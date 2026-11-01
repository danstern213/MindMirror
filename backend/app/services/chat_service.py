from typing import List, Optional, Dict, Any, AsyncGenerator
from datetime import datetime, timezone, date
from uuid import UUID, uuid4
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from fastapi import HTTPException
from openai import AsyncOpenAI
from supabase import Client

from ..models.chat import Message, ChatThread, ChatResponse
from ..models.search import SearchQuery, SearchResult
from ..services.search_service import SearchService
from ..services.storage_service import StorageService
from ..services.settings_service import SettingsService
from ..services.date_query_parser import DateQueryParser
from ..core.config import get_settings
from ..core.utils import count_tokens, truncate_messages_to_fit_limit

settings = get_settings()
logger = logging.getLogger(__name__)

# asyncio only holds a weak reference to a running task, so a task nobody keeps
# a handle to can be garbage collected mid-flight. Park them here until they finish.
_background_tasks: set = set()


def _spawn_background(coro, description: str) -> None:
    """Run a coroutine outside the request's critical path, logging any failure."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    def _log_failure(t: "asyncio.Task") -> None:
        if not t.cancelled() and t.exception() is not None:
            logger.error(f"Background task failed ({description}): {t.exception()}")

    task.add_done_callback(_log_failure)


# Average English text runs ~4 characters per token. Exact tiktoken counts cost a
# full encode pass over every candidate document, which is the single most
# expensive thing in result prioritisation; the real count is still verified
# against the assembled prompt afterwards, so an estimate is safe here.
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


@dataclass
class SearchPlan:
    query: str
    date_start: Optional[date] = None
    date_end: Optional[date] = None
    period: Optional[str] = None  # how to name the range to the model, e.g. "March 2025"


@dataclass
class PromptContext:
    system_content: str
    sources: List[dict]
    plan: SearchPlan
    # Which notes made it in, by section; the context eval reads these.
    recent_titles: List[str]
    range_titles: List[str]
    fragment_titles: List[str]


# Anything that might be a reference to time. A miss here only means the date
# parser runs instead of the model, so it errs wide.
TIME_HINT = re.compile(
    r"\b((19|20)\d{2}|jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sept?(ember)?"
    r"|oct(ober)?|nov(ember)?|dec(ember)?|spring|summer|fall|autumn|winter|q[1-4]|quarter"
    r"|yesterday|today|tonight|week|weekend|month|year|ago|last|this|past|previous|recent(ly)?"
    r"|since|until|during|before|after|early|late|mid|lately|then)\b",
    re.IGNORECASE,
)

SEARCH_PLAN_PROMPT = """You plan searches over the user's personal notes. Each note is dated by the day it was written. Today is {today}.

Given the conversation and the user's latest message, return JSON:
{{"query": "...", "start": "YYYY-MM-DD" or null, "end": "YYYY-MM-DD" or null, "period": "..." or null}}

query: the latest message as one standalone search query. Resolve pronouns and references to earlier turns into the actual people, topics and dates. Leave out the time phrase when you return a date range; if nothing else is left, describe what to look for, e.g. "what I was doing, working on and thinking about".
start/end: only when the message asks about what the user wrote, did or thought during a period of time (including a follow-up about a period named earlier). Whole periods: "March 2025" is 2025-03-01 to 2025-03-31, "2024" is the whole year, "last spring" is March through May of the most recent spring that has ended, "Q1" is January through March. Use null for both when no period is meant, including when a date is only part of a topic ("my notes on the 2008 crisis") or when you cannot tell which dates are meant ("when my daughter was born").
period: a short name for the range, e.g. "March 2025" or "spring 2026"; null without a range."""


def _parse_search_plan(raw: str, today: date) -> Optional[SearchPlan]:
    """The model's JSON as a SearchPlan, or None if it is unusable. Bad dates drop the range, not the query."""
    try:
        data = json.loads(raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(data, dict):
        return None
    query = str(data.get("query") or "").strip()
    if not query:
        return None
    try:
        start = date.fromisoformat(data["start"]) if data.get("start") else None
        end = date.fromisoformat(data["end"]) if data.get("end") else None
    except (TypeError, ValueError):
        start = end = None
    if start and end and start > end:
        start, end = end, start
    if start and not end:
        end = today
    if end and not start:
        start = date(1990, 1, 1)
    period = str(data.get("period") or "").strip() or None if start else None
    return SearchPlan(query=query, date_start=start, date_end=end, period=period)


def _format_datetime_for_db(dt: datetime) -> str:
    """Convert datetime to consistent format for database storage."""
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

def _parse_datetime_from_db(dt_str: str) -> datetime:
    """Parse datetime from database with fallback handling."""
    try:
        # Try direct parsing first
        return datetime.fromisoformat(dt_str)
    except ValueError:
        try:
            # Handle Z suffix format
            if dt_str.endswith('Z'):
                dt_str = dt_str[:-1] + '+00:00'
            return datetime.fromisoformat(dt_str)
        except ValueError:
            # Last resort: strip timezone and parse as UTC
            if '+' in dt_str:
                dt_str_clean = dt_str.split('+')[0]
            elif '-' in dt_str and dt_str.count('-') > 2:  # More than date separators
                dt_str_clean = dt_str.split('-', 3)[0] + '-' + dt_str.split('-', 3)[1] + '-' + dt_str.split('-', 3)[2]
            else:
                dt_str_clean = dt_str
            return datetime.strptime(dt_str_clean, '%Y-%m-%dT%H:%M:%S.%f')

class ChatService:
    """Service for managing chat functionality with database persistence."""

    def __init__(
        self,
        supabase: Client,
        search_service: SearchService,
        storage_service: StorageService,
        settings_service: SettingsService
    ):
        self.supabase = supabase
        self.search_service = search_service
        self.storage_service = storage_service
        self.settings_service = settings_service
        self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.date_query_parser = DateQueryParser()

    async def get_explicitly_referenced_notes(
        self,
        message: str,
        user_id: UUID
    ) -> List[SearchResult]:
        """Extract and process explicitly referenced notes from the message."""
        link_regex = r'\[\[(.*?)\]\]'
        matches = re.finditer(link_regex, message)
        results = []

        for match in matches:
            title = match.group(1)
            # Search for the exact title in the user's files
            search_result = await self.search_service.search_by_title(title, str(user_id))
            if search_result:
                results.append(search_result)

        return results

    async def create_thread(self, user_id: UUID, title: str = "New Chat") -> ChatThread:
        """Create a new chat thread in the database."""
        try:
            thread_id = uuid4()
            
            # Insert the thread into the database
            response = self.supabase.table('chat_threads').insert({
                'id': str(thread_id),
                'title': title,
                'user_id': str(user_id),
                'created': _format_datetime_for_db(datetime.now(timezone.utc)),
                'last_updated': _format_datetime_for_db(datetime.now(timezone.utc))
            }).execute()
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error creating thread: {response.error}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create chat thread in database"
                )
            
            if not response.data:
                raise HTTPException(
                    status_code=500,
                    detail="No data returned when creating thread"
                )
            
            # Create the thread object from the database response
            thread_data = response.data[0]
            thread = ChatThread(
                id=thread_id,
                title=thread_data['title'],
                messages=[],  # Start with empty messages (lazy loading)
                user_id=user_id,
                created=_parse_datetime_from_db(thread_data['created']),
                last_updated=_parse_datetime_from_db(thread_data['last_updated'])
            )
            
            logger.info(f"Created new thread {thread_id} for user {user_id}")
            return thread
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating thread: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create thread: {str(e)}"
            )

    async def get_thread(self, thread_id: UUID, user_id: UUID) -> Optional[ChatThread]:
        """Get a chat thread by ID from the database."""
        try:
            # Get thread metadata
            thread_response = self.supabase.table('chat_threads')\
                .select('*')\
                .eq('id', str(thread_id))\
                .eq('user_id', str(user_id))\
                .single()\
                .execute()
            
            if hasattr(thread_response, 'error') and thread_response.error:
                logger.error(f"Database error fetching thread: {thread_response.error}")
                return None
            
            if not thread_response.data:
                logger.error(f"Thread {thread_id} not found for user {user_id}")
                return None
            
            thread_data = thread_response.data
            
            # Create thread object (messages will be loaded separately when needed)
            thread = ChatThread(
                id=UUID(thread_data['id']),
                title=thread_data['title'],
                messages=[],  # Lazy loading - messages loaded separately
                user_id=UUID(thread_data['user_id']),
                created=_parse_datetime_from_db(thread_data['created']),
                last_updated=_parse_datetime_from_db(thread_data['last_updated'])
            )
            
            return thread
            
        except Exception as e:
            logger.error(f"Error fetching thread {thread_id}: {e}")
            return None

    async def get_user_threads(self, user_id: UUID) -> List[ChatThread]:
        """Get all chat threads for a user from the database."""
        try:
            response = self.supabase.table('chat_threads')\
                .select('*')\
                .eq('user_id', str(user_id))\
                .order('last_updated')\
                .execute()
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error fetching user threads: {response.error}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to load chat history from database"
                )
            
            threads = []
            for thread_data in response.data:
                thread = ChatThread(
                    id=UUID(thread_data['id']),
                    title=thread_data['title'],
                    messages=[],  # Lazy loading - messages loaded separately
                    user_id=UUID(thread_data['user_id']),
                    created=_parse_datetime_from_db(thread_data['created']),
                    last_updated=_parse_datetime_from_db(thread_data['last_updated'])
                )
                threads.append(thread)
            
            return threads
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching user threads: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load chat history: {str(e)}"
            )
    
    async def delete_thread(self, thread_id: UUID, user_id: UUID) -> bool:
        """Delete a chat thread from the database."""
        try:
            # Verify thread belongs to user first
            thread = await self.get_thread(thread_id, user_id)
            if not thread:
                return False
            
            # Delete the thread (CASCADE will handle messages)
            response = self.supabase.table('chat_threads')\
                .delete()\
                .eq('id', str(thread_id))\
                .eq('user_id', str(user_id))\
                .execute()
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error deleting thread: {response.error}")
                return False
            
            logger.info(f"Deleted thread {thread_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting thread {thread_id}: {e}")
            return False
    
    async def add_message(
        self,
        thread_id: UUID,
        role: str,
        content: str,
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> Message:
        """Add a message to a thread in the database."""
        try:
            # Create the message object
            message = Message(
                role=role,
                content=content,
                timestamp=datetime.now(timezone.utc),
                sources=sources
            )
            
            # Insert message into database
            # Convert sources to JSON-serializable format
            serializable_sources = self._serialize_sources_for_json(sources or [])
            
            message_data = {
                'thread_id': str(thread_id),
                'role': role,
                'content': content,
                'created_at': _format_datetime_for_db(message.timestamp),
                'sources': serializable_sources
            }
            
            response = self.supabase.table('chat_messages').insert(message_data).execute()
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error adding message: {response.error}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to save message to database"
                )
            
            # Bookkeeping the caller does not need to wait on. Titling in
            # particular costs a full LLM round-trip, and add_message() is awaited
            # before the response stream opens, so awaiting these here is dead air
            # in front of the user's first token.
            _spawn_background(
                self._update_thread_timestamp(thread_id),
                f"update timestamp for thread {thread_id}"
            )
            if role == 'user':
                _spawn_background(
                    self._update_thread_title_if_needed(thread_id, content),
                    f"generate title for thread {thread_id}"
                )

            return message
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error adding message: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save message: {str(e)}"
            )

    async def get_thread_messages(self, thread_id: UUID, user_id: UUID) -> List[Message]:
        """Lazy load messages for a specific thread."""
        try:
            # Verify thread belongs to user first
            thread = await self.get_thread(thread_id, user_id)
            if not thread:
                raise HTTPException(
                    status_code=404,
                    detail="Chat thread not found or access denied"
                )
            
            # Fetch messages from database
            response = self.supabase.table('chat_messages')\
                .select('*')\
                .eq('thread_id', str(thread_id))\
                .order('created_at')\
                .execute()
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error fetching messages: {response.error}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to load chat messages from database"
                )
            
            messages = []
            for msg_data in response.data:
                message = Message(
                    role=msg_data['role'],
                    content=msg_data['content'],
                    timestamp=_parse_datetime_from_db(msg_data['created_at']),
                    sources=msg_data.get('sources', [])
                )
                messages.append(message)
            
            return messages
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching thread messages: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load chat messages: {str(e)}"
            )

    async def _update_thread_timestamp(self, thread_id: UUID) -> None:
        """Update the last_updated timestamp for a thread."""
        try:
            response = self.supabase.table('chat_threads')\
                .update({'last_updated': _format_datetime_for_db(datetime.now(timezone.utc))})\
                .eq('id', str(thread_id))\
                .execute()
            
            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error updating thread timestamp: {response.error}")
        except Exception as e:
            logger.error(f"Failed to update thread timestamp: {e}")

    async def _update_thread_title_if_needed(self, thread_id: UUID, first_message: str) -> None:
        """Update thread title if it's still the default 'New Chat'."""
        try:
            thread_response = self.supabase.table('chat_threads')\
                .select('title')\
                .eq('id', str(thread_id))\
                .single()\
                .execute()

            if hasattr(thread_response, 'error') or not thread_response.data:
                return

            if thread_response.data['title'] != "New Chat":
                return

            new_title = await self._generate_thread_title(first_message)

            response = self.supabase.table('chat_threads')\
                .update({'title': new_title})\
                .eq('id', str(thread_id))\
                .execute()

            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error updating thread title: {response.error}")
            else:
                logger.info(f"Updated thread {thread_id} title to: {new_title}")

        except Exception as e:
            logger.error(f"Failed to update thread title: {e}")

    async def _generate_thread_title(self, first_message: str) -> str:
        """Use LLM to generate a short descriptive thread title from the first message."""
        try:
            response = await self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Generate a concise, descriptive title for a chat thread based on the user's first message. "
                            "The title should capture the topic or intent clearly. "
                            "Maximum 40 characters. No quotes. No punctuation at the end."
                        )
                    },
                    {"role": "user", "content": first_message[:500]}
                ],
                max_completion_tokens=20
            )
            title = response.choices[0].message.content.strip().strip('"\'')
            if len(title) > 40:
                title = title[:37] + "..."
            return title or first_message[:37] + "..."
        except Exception as e:
            logger.error(f"Failed to generate thread title via LLM: {e}")
            # Fall back to truncating the message
            msg = first_message.strip()
            return msg[:37] + "..." if len(msg) > 40 else msg

    async def _plan_search(
        self, message: str, history: List[Dict[str, str]], today: Optional[date] = None
    ) -> SearchPlan:
        """
        What to search for: a standalone query and, if the message asks about a
        period of time, its date range.

        Follow-ups ("what about the second one?") need the conversation to mean
        anything, and time can be said a hundred ways ("last spring", "Q1 2025",
        "the year before last"), so a model reads the message instead of a list
        of patterns. Skipped when the message has no history and no hint of
        time, to keep plain questions fast. If the model fails, the regex parser
        still catches the common phrasings.
        """
        if not history and not TIME_HINT.search(message):
            return SearchPlan(query=message)

        today = today or date.today()
        transcript = "\n".join(f"{m['role']}: {m['content'][:1000]}" for m in history[-6:])
        try:
            response = await self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SEARCH_PLAN_PROMPT.format(today=today.isoformat())},
                    {"role": "user", "content": (f"Conversation:\n{transcript}\n\n" if transcript else "")
                        + f"Latest message: {message}"}
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=300
            )
            plan = _parse_search_plan(response.choices[0].message.content or "", today)
            if plan:
                logger.info(f"Search plan for {message[:60]!r}: {plan}")
                return plan
        except Exception as e:
            logger.warning(f"Search planning failed, falling back to the date parser: {e}")

        parsed = self.date_query_parser.parse_query(message)
        if parsed.has_temporal_intent and parsed.date_range:
            return SearchPlan(query=parsed.clean_query, date_start=parsed.date_range.start,
                              date_end=parsed.date_range.end, period=parsed.temporal_description)
        return SearchPlan(query=message)

    def _generate_context(self, search_results: List[dict], temporal_description: Optional[str] = None) -> str:
        """Generate formatted context from search results."""
        referenced_notes = set()
        context_parts = []

        # Add temporal context header if we have a date-based query
        if temporal_description:
            context_parts.append(f"[Temporal Query: Looking for notes from {temporal_description}]")

        for result in search_results:
            referenced_notes.add(result['title'])

            # Determine relevance indicator
            relevance_indicator = "Explicitly Referenced" if result.get('explicit') else \
                "Highly Relevant" if result['score'] > 0.9 else "Relevant"

            # Build context text with detailed metadata
            context_text = f"[From [[{result['title']}]]] ({relevance_indicator}"
            if not result.get('explicit'):
                context_text += f", score: {result['score']:.3f}"
            if result.get('keyword_score'):
                context_text += f", keyword relevance: {result['keyword_score']:.3f}"
            if result.get('matched_keywords'):
                context_text += f", matched terms: {', '.join(result['matched_keywords'])}"
            # Include document date if available
            if result.get('document_date'):
                doc_date = result['document_date']
                if hasattr(doc_date, 'strftime'):
                    context_text += f", date: {doc_date.strftime('%Y-%m-%d')}"
                else:
                    context_text += f", date: {doc_date}"
            context_text += f")\n\nRelevant Section:\n{result['content']}"

            context_parts.append(context_text)

        # Join all parts with separator
        context = "\n\n==========\n\n".join(context_parts)

        # Add footer with referenced notes
        if referenced_notes:
            context += "\n\n---\nBased on the following context:\n"
            context += "\n".join(f"- [[{path}]]" for path in sorted(referenced_notes))

        return context

    def _format_recent_notes(self, notes: List[SearchResult]) -> str:
        if not notes:
            return "(no notes in this period)"
        return "\n\n==========\n\n".join(
            f"[[{n.title}]]" + (f" ({n.document_date.isoformat()})" if n.document_date else "") + f"\n{n.content}"
            for n in notes
        )

    def _serialize_sources_for_json(self, sources: List[dict]) -> List[dict]:
        """Convert sources to JSON-serializable format by converting UUIDs and dates to strings."""
        if not sources:
            return []

        serializable_sources = []
        for source in sources:
            serializable_source = {}
            for key, value in source.items():
                if isinstance(value, UUID):
                    serializable_source[key] = str(value)
                elif isinstance(value, date):
                    serializable_source[key] = value.isoformat()
                else:
                    serializable_source[key] = value
            serializable_sources.append(serializable_source)

        return serializable_sources

    def _prioritize_search_results(self, search_results: List[dict], token_budget: int = 20000) -> List[dict]:
        """
        Prioritize search results to fit within a token budget while maintaining relevant context.
        
        Strategy:
        1. Keep explicitly referenced documents (always highest priority)
        2. Sort remaining by relevance score
        3. Keep high-scoring results until budget exhausted
        
        Args:
            search_results: List of search result dictionaries
            token_budget: Maximum tokens to allocate for results
            
        Returns:
            List[dict]: Prioritized and potentially filtered results
        """
        if not search_results:
            return []
            
        # First, separate explicit references and regular results
        explicit_refs = []
        scored_results = []
        
        for result in search_results:
            if result.get('explicit', False):
                explicit_refs.append(result)
            else:
                scored_results.append(result)
        
        # Sort regular results by score (descending)
        scored_results.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # Start with explicit references (these are kept regardless of budget)
        prioritized_results = explicit_refs.copy()
        
        # Calculate current token usage
        context_text = self._generate_context(prioritized_results)
        current_tokens = _estimate_tokens(context_text)
        
        # If we're already over budget with just explicit refs, we need to truncate their content later
        if current_tokens > token_budget:
            logger.warning(f"Explicit references alone exceed token budget ({current_tokens} > {token_budget})")
            # Still return them all, but content will be truncated later
            return prioritized_results
        
        # Add highest scoring results until we hit the budget
        remaining_budget = token_budget - current_tokens
        
        for result in scored_results:
            # Roughly estimate tokens for this result
            result_text = self._generate_context([result])
            result_tokens = _estimate_tokens(result_text)
            
            if result_tokens < remaining_budget:
                prioritized_results.append(result)
                remaining_budget -= result_tokens
            # A long note that doesn't fit shouldn't stop shorter, lower-ranked
            # ones that do, so keep going rather than break.
                
        logger.info(f"Prioritized {len(prioritized_results)} out of {len(search_results)} search results to fit token budget")
        return prioritized_results
        
    async def _build_prompt(
        self, content: str, history: List[Dict[str, str]], user_id: UUID, today: Optional[date] = None
    ) -> PromptContext:
        """
        The system prompt for one message: instructions, who the user is, the
        last month of notes whole, every note from a period the message asks
        about, and search fragments from everything else.
        """
        plan = await self._plan_search(content, history, today)

        user_settings, semantic_results, explicit_results, recent_notes = await asyncio.gather(
            self.settings_service.get_user_settings(user_id),
            self.search_service.search(SearchQuery(
                query=plan.query, user_id=user_id, date_start=plan.date_start, date_end=plan.date_end
            )),
            self.get_explicitly_referenced_notes(content, user_id),
            self.search_service.get_recent_notes(
                user_id, settings.RECENT_NOTES_DAYS, settings.RECENT_NOTES_TOKEN_BUDGET
            ),
        )

        # An explicit [[link]] wins over everything, so it is never dropped;
        # recent notes are already in whole, so search should not repeat them.
        explicit_dicts = [result.model_dump() for result in explicit_results]
        explicit_ids = {d['id'] for d in explicit_dicts}
        recent_notes = [n for n in recent_notes if n.id not in explicit_ids]
        in_prompt_ids = explicit_ids | {n.id for n in recent_notes}

        # A question about a period gets that period's notes whole. Past about a
        # year the notes stop fitting and the most relevant fragments do better.
        range_notes: List[SearchResult] = []
        range_total = 0
        fragments_budget = settings.RETRIEVED_NOTES_TOKEN_BUDGET
        if plan.date_start and plan.date_end and \
                (plan.date_end - plan.date_start).days <= settings.MAX_DATE_RANGE_DAYS:
            range_notes, range_total = await self.search_service.get_notes_in_range(
                user_id, plan.date_start, plan.date_end, settings.DATE_RANGE_TOKEN_BUDGET,
                ranked_ids=[r.id for r in semantic_results],
            )
            range_notes = [n for n in range_notes if n.id not in in_prompt_ids]
            in_prompt_ids |= {n.id for n in range_notes}
            # Search was limited to the same range, so its fragments mostly
            # repeat these notes; half the space is plenty for the rest.
            fragments_budget //= 2

        semantic_dicts = [r.model_dump() for r in semantic_results if r.id not in in_prompt_ids]
        prioritized_results = self._prioritize_search_results(
            explicit_dicts + semantic_dicts, token_budget=fragments_budget
        )
        context = self._generate_context(prioritized_results, plan.period)

        range_section = ""
        if range_notes:
            shown = f"all {len(range_notes)}" if len(range_notes) == range_total \
                else f"the {len(range_notes)} most relevant of {range_total}"
            range_section = f"""

NOTES FROM {plan.period or f'{plan.date_start} to {plan.date_end}'} ({shown} notes from this period not already shown above, in full, oldest first; the user is asking about this period, so answer from these and cite them):

{self._format_recent_notes(range_notes)}"""

        # Stable parts first (instructions, who the user is, this month's
        # notes) so consecutive messages share a long prefix and hit OpenAI's
        # automatic prompt cache; per-message notes last.
        system_content = f"""{settings.SYSTEM_PROMPT}

ABOUT THE USER:
{user_settings.get('personal_info') or '(not provided)'}

MEMORY:
{user_settings.get('memory') or '(none)'}

TODAY: {date.today().strftime('%A, %B %d, %Y')}

RECENT NOTES (the last {settings.RECENT_NOTES_DAYS} days, in full, oldest first; this is what is on their mind now):

{self._format_recent_notes(recent_notes)}{range_section}

OLDER NOTES RELEVANT TO THIS MESSAGE (found by search; fragments, not whole notes):

{context}"""

        return PromptContext(
            system_content=system_content,
            sources=[n.model_dump() for n in range_notes] + prioritized_results,
            plan=plan,
            recent_titles=[n.title for n in recent_notes],
            range_titles=[n.title for n in range_notes],
            fragment_titles=[r['title'] for r in prioritized_results],
        )

    async def process_message(
        self,
        content: str,
        thread_id: Optional[UUID],
        user_id: UUID
    ) -> AsyncGenerator[ChatResponse, None]:
        """Process a user message and generate a response."""
        logger.info(f"[PROCESS_MESSAGE] process_message started - user_id: {user_id}, thread_id: {thread_id}, content_preview: {content[:50]}...")
        try:
            # History first: it both verifies the thread belongs to this user and
            # tells us what a follow-up question is referring to.
            history_messages: List[Dict[str, str]] = []
            if thread_id:
                prior = await self.get_thread_messages(thread_id, user_id)
                history_messages = [{"role": m.role, "content": m.content} for m in prior[-20:]]  # ~10 turns
                logger.info(f"[PROCESS_MESSAGE] Loaded {len(history_messages)} history messages from thread {thread_id}")

            prompt = await self._build_prompt(content, history_messages, user_id)
            system_content = prompt.system_content
            prioritized_results = prompt.sources

            if thread_id:
                await self.add_message(thread_id, "user", content)

            messages = [
                {"role": "system", "content": system_content},
                *history_messages,
                {"role": "user", "content": content}
            ]

            # Each part of the prompt is budgeted above, so this only trips on a
            # very long thread; it drops the oldest turns and keeps everything else.
            messages = truncate_messages_to_fit_limit(
                messages,
                model=settings.OPENAI_MODEL,
                max_tokens=settings.MAX_PROMPT_TOKENS,
                preserve_system_message=True,
                preserve_last_user_message=True
            )
            token_count = count_tokens(messages, settings.OPENAI_MODEL)

            # Get the chat completion stream
            logger.info(f"[PROCESS_MESSAGE] Calling OpenAI API - model: {settings.OPENAI_MODEL}, message_count: {len(messages)}, token_count: {token_count}")
            try:
                # GPT-5 models require max_completion_tokens instead of max_tokens
                model_lower = settings.OPENAI_MODEL.lower()
                is_gpt5 = "gpt-5" in model_lower or "chatgpt-5" in model_lower
                
                # Build the API call parameters - different for GPT-5 vs older models
                api_params = {
                    "model": settings.OPENAI_MODEL,
                    "messages": messages,
                    "stream": True
                }
                
                # Use the correct parameters based on model version
                if is_gpt5:
                    # GPT-5 models have restrictions:
                    # - Use max_completion_tokens instead of max_tokens
                    # - Don't support temperature, top_p, frequency_penalty, presence_penalty
                    #   (these are only allowed when reasoning.effort="none", which is not the default)
                    try:
                        api_params["max_completion_tokens"] = 4000
                        stream = await self.openai_client.chat.completions.create(**api_params)
                    except TypeError as e:
                        # SDK version is too old and doesn't support max_completion_tokens
                        # Omit the parameter - API will use its default max_completion_tokens
                        logger.warning(
                            f"OpenAI SDK doesn't support max_completion_tokens. "
                            f"Omitting parameter for {settings.OPENAI_MODEL}. "
                            f"Please upgrade SDK: pip install --upgrade openai"
                        )
                        api_params.pop("max_completion_tokens", None)
                        stream = await self.openai_client.chat.completions.create(**api_params)
                else:
                    # For older models, use standard parameters
                    api_params.update({
                        "temperature": 0.7,
                        "top_p": 1,
                        "frequency_penalty": 0,
                        "presence_penalty": 0,
                        "max_tokens": 4000
                    })
                    stream = await self.openai_client.chat.completions.create(**api_params)
                
                logger.info("[PROCESS_MESSAGE] OpenAI stream created successfully")
            except Exception as e:
                logger.error(f"[PROCESS_MESSAGE] Failed to create OpenAI stream: {e}", exc_info=True)
                raise

            # Process the stream
            current_content = ""
            # Serialize sources once for all responses
            serialized_sources = self._serialize_sources_for_json(prioritized_results)
            
            # Yield an initial status message to let the frontend know streaming has started
            # This prevents the frontend from hanging while waiting for the first chunk
            logger.info("[PROCESS_MESSAGE] Yielding initial status message")
            yield ChatResponse(
                content="",  # Empty content for status update
                sources=serialized_sources,
                thread_id=thread_id or UUID(int=0),
                done=False
            )
            
            chunk_count = 0
            logger.info("[PROCESS_MESSAGE] Starting to iterate over OpenAI stream")
            first_chunk_received = False
            try:
                async for chunk in stream:
                    chunk_count += 1
                    if not first_chunk_received:
                        first_chunk_received = True
                        logger.info(f"[PROCESS_MESSAGE] First chunk received (#{chunk_count})")
                    
                    if chunk.choices and len(chunk.choices) > 0:
                        if chunk.choices[0].delta.content is not None:
                            content_delta = chunk.choices[0].delta.content
                            current_content += content_delta
                            logger.debug(f"[PROCESS_MESSAGE] Received chunk #{chunk_count}, delta_length: {len(content_delta)}, total_content_length: {len(current_content)}")
                            yield ChatResponse(
                                content=content_delta,
                                sources=serialized_sources,  # Use serialized sources
                                thread_id=thread_id or UUID(int=0),
                                done=False
                            )
                        else:
                            logger.debug(f"[PROCESS_MESSAGE] Chunk #{chunk_count} has no content delta")
                    else:
                        logger.warning(f"[PROCESS_MESSAGE] Chunk #{chunk_count} has no choices")
                
                if not first_chunk_received:
                    logger.warning("[PROCESS_MESSAGE] Stream completed but no chunks were received")
                else:
                    logger.info(f"[PROCESS_MESSAGE] Stream iteration complete - total chunks: {chunk_count}, final content length: {len(current_content)}")
            except Exception as e:
                logger.error(f"[PROCESS_MESSAGE] Error iterating over stream: {e}", exc_info=True)
                if not first_chunk_received:
                    logger.error("[PROCESS_MESSAGE] Stream failed before receiving any chunks - this may indicate a connection or API issue")
                raise

            # Save the assistant's message to the thread if we have one
            if thread_id:
                try:
                    await self.add_message(
                        thread_id,
                        "assistant",
                        current_content,
                        sources=serialized_sources  # Use serialized sources
                    )
                except Exception as e:
                    logger.error(f"Error saving assistant message: {e}")
                    # Don't fail the entire request, but log the error
                    # The user will still get their response, just won't be saved

            # Yield final message
            yield ChatResponse(
                content="",  # Don't send content in final message
                sources=serialized_sources,  # Use serialized sources
                thread_id=thread_id or UUID(int=0),
                done=True
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process message: {str(e)}"
            ) 