from typing import List, Optional, Dict, Any, AsyncGenerator
from datetime import datetime, timezone, date
from uuid import UUID, uuid4
import logging
import json
import re
from fastapi import HTTPException
from openai import AsyncOpenAI
from supabase import Client

from ..models.chat import Message, ChatThread, ChatResponse
from ..models.search import SearchQuery, SearchResult
from ..services.search_service import SearchService
from ..services.storage_service import StorageService
from ..services.date_query_parser import DateQueryParser
from ..core.config import get_settings
from ..core.utils import count_tokens, truncate_messages_to_fit_limit

settings = get_settings()
logger = logging.getLogger(__name__)

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
        storage_service: StorageService
    ):
        self.supabase = supabase
        self.search_service = search_service
        self.storage_service = storage_service
        self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.date_query_parser = DateQueryParser()
        # User-specific settings
        self.user_settings: Dict[UUID, Dict[str, str]] = {}
    
    def get_user_settings(self, user_id: UUID) -> Dict[str, str]:
        """Get user-specific settings, with defaults if not set."""
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {
                "personal_info": "",
                "memory": ""
            }
        return self.user_settings[user_id]

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
            
            # Update thread's last_updated timestamp
            await self._update_thread_timestamp(thread_id)
            
            # If this is the first user message, update the thread title
            if role == 'user':
                await self._update_thread_title_if_needed(thread_id, content)
            
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
            # Check if current title is the default
            thread_response = self.supabase.table('chat_threads')\
                .select('title')\
                .eq('id', str(thread_id))\
                .single()\
                .execute()
            
            if hasattr(thread_response, 'error') or not thread_response.data:
                return
            
            current_title = thread_response.data['title']
            if current_title == "New Chat":
                # Generate new title from first message
                new_title = first_message.strip()
                if len(new_title) > 50:  # Truncate if too long
                    new_title = new_title[:47] + "..."
                
                # Update the title
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

    async def analyze_conversation_continuity(
        self,
        message: str,
        thread_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """Analyze if the message is a follow-up to the previous conversation."""
        if not thread_id:
            return {
                'is_follow_up': False,
                'search_query': message,
                'context': message
            }

        # Get thread history
        thread = await self.get_thread(thread_id, user_id)
        if not thread or len(thread.messages) < 2:
            return {
                'is_follow_up': False,
                'search_query': message,
                'context': message
            }

        # Get last exchange
        messages = thread.messages
        last_messages = messages[-3:]  # Get last 3 messages for context

        try:
            analysis_messages = [
                {
                    "role": "system",
                    "content": """Analyze the conversation continuity between messages. Determine if the new message is:
                    1. A follow-up/clarification of the previous topic
                    2. A new, unrelated topic
                    
                    Respond in JSON format:
                    {
                        "isFollowUp": boolean,
                        "explanation": string,
                        "searchQuery": string (if follow-up, combine relevant context from previous exchange with new query; if new topic, use just the new message)
                    }"""
                },
                *[{"role": msg.role, "content": msg.content} for msg in last_messages[:-1]],
                {"role": "user", "content": message}
            ]
            
            # Check token count and truncate if needed
            token_count = count_tokens(analysis_messages, settings.OPENAI_MODEL)
            logger.info(f"Analysis messages token count: {token_count}")
            
            # If over tokens limit, truncate
            if token_count > 28500:  # Using more conservative limit with safety margin
                logger.warning(f"Analysis token count ({token_count}) is high. Truncating.")
                analysis_messages = truncate_messages_to_fit_limit(
                    analysis_messages,
                    model=settings.OPENAI_MODEL,
                    max_tokens=28500,
                    preserve_system_message=True,
                    preserve_last_user_message=True
                )
                token_count = count_tokens(analysis_messages, settings.OPENAI_MODEL)
                logger.info(f"Analysis messages token count after truncation: {token_count}")

            response = await self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=analysis_messages,
                temperature=0.1
            )

            analysis = json.loads(response.choices[0].message.content)
            
            return {
                'is_follow_up': analysis['isFollowUp'],
                'search_query': analysis['searchQuery'],
                'context': "\n".join(msg.content for msg in last_messages) if analysis['isFollowUp'] else message
            }
        except Exception as error:
            logger.error(f"Error analyzing conversation continuity: {error}")
            return {
                'is_follow_up': False,
                'search_query': message,
                'context': message
            }

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
            
        # Import here to avoid circular imports
        from ..core.utils import count_tokens
        
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
        current_tokens = count_tokens([{"role": "system", "content": context_text}], settings.OPENAI_MODEL)
        
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
            result_tokens = count_tokens([{"role": "system", "content": result_text}], settings.OPENAI_MODEL)
            
            if result_tokens < remaining_budget:
                prioritized_results.append(result)
                remaining_budget -= result_tokens
            else:
                # Stop adding results once we hit the budget
                break
                
        logger.info(f"Prioritized {len(prioritized_results)} out of {len(search_results)} search results to fit token budget")
        return prioritized_results
        
    async def process_message(
        self,
        content: str,
        thread_id: Optional[UUID],
        user_id: UUID
    ) -> AsyncGenerator[ChatResponse, None]:
        """Process a user message and generate a response."""
        logger.info(f"[PROCESS_MESSAGE] process_message started - user_id: {user_id}, thread_id: {thread_id}, content_preview: {content[:50]}...")
        try:
            # Get user settings
            user_settings = self.get_user_settings(user_id)
            
            # Get conversation analysis
            conversation_analysis = await self.analyze_conversation_continuity(content, thread_id, user_id) if thread_id else {
                'is_follow_up': False,
                'context': ''
            }

            # Parse query for temporal intent
            parsed_query = self.date_query_parser.parse_query(content)
            temporal_description = None
            if parsed_query.has_temporal_intent:
                logger.info(f"Detected temporal query: {parsed_query.temporal_description} (range: {parsed_query.date_range})")
                temporal_description = parsed_query.temporal_description

            # Perform semantic search with date filtering if applicable
            search_query = SearchQuery(
                query=parsed_query.clean_query if parsed_query.has_temporal_intent else content,
                user_id=user_id,
                date_start=parsed_query.date_range.start if parsed_query.date_range else None,
                date_end=parsed_query.date_range.end if parsed_query.date_range else None
            )
            semantic_results = await self.search_service.search(search_query)
            
            # Get explicitly referenced notes
            explicit_results = await self.get_explicitly_referenced_notes(content, user_id)
            
            # Convert SearchResult objects to dictionaries and combine results
            explicit_dicts = [result.model_dump() for result in explicit_results]
            semantic_dicts = [result.model_dump() for result in semantic_results 
                            if result.model_dump() not in explicit_dicts]
            all_results = explicit_dicts + semantic_dicts
            
            # Prioritize results to fit within token budget before generating context
            # Use a lower budget to leave room for system message and conversation
            prioritized_results = self._prioritize_search_results(all_results, token_budget=20000)

            # Generate context using prioritized results
            context = self._generate_context(prioritized_results, temporal_description)

            # If we have a thread, add the user message to it
            if thread_id:
                try:
                    # Verify thread exists and belongs to user
                    thread = await self.get_thread(thread_id, user_id)
                    if not thread:
                        raise HTTPException(
                            status_code=404,
                            detail="Chat thread not found or access denied. Please refresh the page and try again."
                        )
                    
                    # Add user message to database
                    await self.add_message(thread_id, "user", content)
                    
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Error saving user message to thread: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to save your message. Please try again or refresh the page."
                    )

            # Prepare messages for AI with enhanced context
            system_content = f"""{settings.SYSTEM_PROMPT}

MEMORY CONTEXT:
{user_settings['memory']}

ABOUT THE USER:
{user_settings['personal_info']}

Conversation Analysis:
{"This is a follow-up question to the previous topic. Consider the previous context while maintaining focus on new information." if conversation_analysis['is_follow_up'] else "This is a new topic. Focus on providing fresh information without being constrained by the previous conversation."}

Current conversation context:
{conversation_analysis['context']}

Here are the relevant notes and their context:

{context}"""

            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": content}
            ]
            
            # Check token count and truncate if necessary
            token_count = count_tokens(messages, settings.OPENAI_MODEL)
            logger.info(f"Initial message token count: {token_count}")
            
            # If token count exceeds limit, truncate content
            max_tokens = 28500  # More conservative limit with safety margin
            if token_count > max_tokens:
                logger.warning(f"Message token count ({token_count}) exceeds limit. Truncating context.")
                
                # First, try to truncate the system message context selectively
                # We want to keep most of the context but reduce it in a smart way
                system_lines = system_content.split("\n")
                context_start = next((i for i, line in enumerate(system_lines) if line == "Here are the relevant notes and their context:"), -1)
                
                if context_start != -1 and context_start < len(system_lines) - 1:
                    # We found the context section, let's truncate it intelligently
                    
                    # Calculate how many tokens we need to remove
                    tokens_to_remove = token_count - max_tokens + 500  # With a small buffer
                    logger.info(f"Need to remove approximately {tokens_to_remove} tokens")
                    
                    # Get just the context part
                    context_lines = system_lines[context_start + 1:]
                    context_text = "\n".join(context_lines)
                    
                    # Estimate tokens per line for context (rough approximation)
                    context_tokens = count_tokens([{"role": "system", "content": context_text}], settings.OPENAI_MODEL)
                    logger.info(f"Context section has approximately {context_tokens} tokens")
                    
                    if context_tokens > tokens_to_remove:
                        # We can just reduce the context rather than removing it all
                        # Keep a proportional amount of each context section
                        keep_ratio = 1 - (tokens_to_remove / context_tokens)
                        keep_ratio = max(0.5, keep_ratio)  # Keep at least 50%
                        logger.info(f"Keeping approximately {keep_ratio*100:.2f}% of context")
                        
                        # Find the = separators which divide different notes
                        separator_indices = [i for i, line in enumerate(context_lines) if line.startswith("==========")]
                        
                        if separator_indices:
                            # We have multiple sections, keep a balanced portion of each
                            sections = []
                            last_idx = 0
                            
                            for idx in separator_indices:
                                sections.append(context_lines[last_idx:idx])
                                last_idx = idx
                            
                            # Add the last section
                            sections.append(context_lines[last_idx:])
                            
                            # Keep the most important parts of each section
                            truncated_context = []
                            for section in sections:
                                # For each section, keep the beginning (title and metadata) and a portion of content
                                if len(section) <= 5:  # Very short section, keep it all
                                    truncated_context.extend(section)
                                else:
                                    # Keep headers and beginning intact (typically first 3-5 lines)
                                    header_lines = min(5, len(section) // 3)
                                    # Keep a proportion of the rest based on our ratio
                                    content_to_keep = int((len(section) - header_lines) * keep_ratio)
                                    truncated_context.extend(section[:header_lines])
                                    if content_to_keep > 0:
                                        truncated_context.append("[...context truncated to fit token limit...]")
                                        truncated_context.extend(section[header_lines:header_lines+content_to_keep])
                            
                            # Recombine the truncated context
                            truncated_system_content = "\n".join(
                                system_lines[:context_start + 1] + truncated_context
                            )
                        else:
                            # Only one big section, keep beginning and end
                            content_lines = len(context_lines)
                            keep_lines = int(content_lines * keep_ratio)
                            
                            # Always keep beginning (metadata)
                            beginning_lines = min(5, content_lines // 5)
                            # Use remaining budget for content, prioritizing beginning and some end
                            remaining = keep_lines - beginning_lines
                            
                            if remaining > 10:
                                # Keep some from beginning and some from end
                                from_beginning = int(remaining * 0.7)  # Prioritize beginning
                                from_end = remaining - from_beginning
                                
                                truncated_context = (
                                    context_lines[:beginning_lines + from_beginning] + 
                                    ["[...context truncated to fit token limit...]"] + 
                                    (context_lines[-from_end:] if from_end > 0 else [])
                                )
                            else:
                                # Not enough remaining, just keep from beginning
                                truncated_context = (
                                    context_lines[:beginning_lines + remaining] +
                                    ["[...context truncated to fit token limit...]"]
                                )
                            
                            truncated_system_content = "\n".join(
                                system_lines[:context_start + 1] + truncated_context
                            )
                    else:
                        # If context isn't much larger than what we need to remove,
                        # preserve system message structure but thin out context
                        truncated_system_content = "\n".join(
                            system_lines[:context_start + 1] + 
                            ["[Context truncated to fit token limit]"] +
                            # Keep only document titles and metadata
                            [line for line in context_lines if line.startswith("[From [[") 
                             or "score:" in line or "keyword relevance:" in line]
                        )
                    
                    messages[0]["content"] = truncated_system_content
                    
                    # Recalculate token count
                    token_count = count_tokens(messages, settings.OPENAI_MODEL)
                    logger.info(f"Token count after smart context truncation: {token_count}")
                
                # If still over limit, use the more aggressive truncation function as a fallback
                if token_count > max_tokens:
                    messages = truncate_messages_to_fit_limit(
                        messages, 
                        model=settings.OPENAI_MODEL,
                        max_tokens=max_tokens,
                        preserve_system_message=True,
                        preserve_last_user_message=True
                    )
                    
                    # Recalculate token count
                    token_count = count_tokens(messages, settings.OPENAI_MODEL)
                    logger.info(f"Final message token count after truncation: {token_count}")
            
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