from typing import List, Optional, Dict, Any, AsyncGenerator
from datetime import datetime
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
from ..core.config import get_settings
from ..core.utils import count_tokens, truncate_messages_to_fit_limit

settings = get_settings()
logger = logging.getLogger(__name__)

class ChatService:
    """Service for managing chat functionality."""
    
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
        # In-memory storage for threads
        self.threads: Dict[UUID, ChatThread] = {}
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
        """Create a new chat thread."""
        thread_id = uuid4()
        thread = ChatThread(
            id=thread_id,
            title=title,
            messages=[],
            user_id=user_id,
            created=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
        self.threads[thread_id] = thread
        logger.info(f"Created new thread {thread_id} for user {user_id}")
        return thread

    async def get_thread(self, thread_id: UUID, user_id: UUID) -> Optional[ChatThread]:
        """Get a chat thread by ID."""
        thread = self.threads.get(thread_id)
        if not thread:
            logger.error(f"Thread {thread_id} not found")
            return None
        if thread.user_id != user_id:
            logger.error(f"Thread {thread_id} belongs to user {thread.user_id}, not {user_id}")
            return None
        return thread

    async def get_user_threads(self, user_id: UUID) -> List[ChatThread]:
        """Get all chat threads for a user."""
        return [
            thread for thread in self.threads.values()
            if thread.user_id == user_id
        ]
    
    async def delete_thread(self, thread_id: UUID, user_id: UUID) -> bool:
        """Delete a chat thread."""
        thread = self.threads.get(thread_id)
        if thread and thread.user_id == user_id:
            del self.threads[thread_id]
            return True
        return False
    
    async def add_message(
        self,
        thread_id: UUID,
        role: str,
        content: str,
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> Message:
        """Add a message to a thread."""
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.utcnow(),
            sources=sources
        )
        
        thread = self.threads.get(thread_id)
        if not thread:
            raise Exception("Thread not found")
            
        thread.messages.append(message)
        thread.last_updated = datetime.utcnow()
        return message
    
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

    def _generate_context(self, search_results: List[dict]) -> str:
        """Generate formatted context from search results."""
        referenced_notes = set()
        context_parts = []
        
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
            context_text += f")\n\nRelevant Section:\n{result['content']}"

            context_parts.append(context_text)

        # Join all parts with separator
        context = "\n\n==========\n\n".join(context_parts)

        # Add footer with referenced notes
        if referenced_notes:
            context += "\n\n---\nBased on the following context:\n"
            context += "\n".join(f"- [[{path}]]" for path in sorted(referenced_notes))

        return context

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
        try:
            # Get user settings
            user_settings = self.get_user_settings(user_id)
            
            # Get conversation analysis
            conversation_analysis = await self.analyze_conversation_continuity(content, thread_id, user_id) if thread_id else {
                'is_follow_up': False,
                'context': ''
            }
            
            # Perform semantic search
            search_query = SearchQuery(query=content, user_id=user_id)
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
            context = self._generate_context(prioritized_results)

            # If we have a thread, add the message to it
            if thread_id:
                try:
                    thread = await self.get_thread(thread_id, user_id)
                    if thread:
                        await self.add_message(thread_id, "user", content)
                except Exception as e:
                    logger.warning(f"Non-critical error handling thread: {e}")

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
            stream = await self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=4000,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                stream=True
            )

            # Process the stream
            current_content = ""
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    content_delta = chunk.choices[0].delta.content
                    current_content += content_delta
                    yield ChatResponse(
                        content=content_delta,
                        sources=prioritized_results,  # Use prioritized results
                        thread_id=thread_id or UUID(int=0),
                        done=False
                    )

            # Save the assistant's message to the thread if we have one
            if thread_id:
                try:
                    await self.add_message(
                        thread_id,
                        "assistant",
                        current_content,
                        sources=prioritized_results  # Use prioritized results
                    )
                except Exception as e:
                    logger.warning(f"Non-critical error saving assistant message: {e}")

            # Yield final message
            yield ChatResponse(
                content="",  # Don't send content in final message
                sources=prioritized_results,  # Use prioritized results
                thread_id=thread_id or UUID(int=0),
                done=True
            )

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process message: {str(e)}"
            ) 