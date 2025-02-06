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
        thread_id: UUID
    ) -> Dict[str, Any]:
        """Analyze if the message is a follow-up to the previous conversation."""
        thread = self.threads.get(thread_id)
        if not thread or len(thread.messages) < 2:
            return {
                'is_follow_up': False,
                'search_query': message,
                'context': message
            }

        # Get last exchange
        last_messages = [msg for msg in thread.messages[-2:] if msg.role in ["user", "assistant"]]
        if len(last_messages) < 2:
            return {
                'is_follow_up': False,
                'search_query': message,
                'context': message
            }

        try:
            response = await self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
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
                    {"role": "user", "content": last_messages[-2].content},
                    {"role": "assistant", "content": last_messages[-1].content},
                    {"role": "user", "content": message}
                ],
                temperature=0.1
            )
            
            analysis = json.loads(response.choices[0].message.content)
            
            return {
                'is_follow_up': analysis['isFollowUp'],
                'search_query': analysis['searchQuery'],
                'context': f"{last_messages[-2].content}\n{last_messages[-1].content}\n{message}" if analysis['isFollowUp'] else message
            }
        except Exception as e:
            logger.error(f"Error analyzing conversation continuity: {e}")
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
            
            # Build context text
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

    async def process_message(
        self,
        content: str,
        thread_id: Optional[UUID],
        user_id: UUID
    ) -> AsyncGenerator[ChatResponse, None]:
        """Process a user message and generate a streaming response."""
        try:
            # Get user settings
            user_settings = self.get_user_settings(user_id)
            
            # Get explicitly referenced notes first
            explicit_results = await self.get_explicitly_referenced_notes(content, user_id)
            
            # Then get semantic search results
            # Note: We intentionally limit to 3 results for chat context to:
            # 1. Focus on the most relevant content
            # 2. Keep context concise for better AI responses
            # 3. Manage token usage
            CHAT_CONTEXT_LIMIT = 3
            semantic_results = await self.search_service.search(
                SearchQuery(
                    query=content,
                    user_id=user_id,
                    top_k=CHAT_CONTEXT_LIMIT  # Override default limit for chat context
                )
            )

            # Convert SearchResult objects to dictionaries and combine results
            explicit_dicts = [result.model_dump() for result in explicit_results]
            semantic_dicts = [result.model_dump() for result in semantic_results 
                            if result.model_dump() not in explicit_dicts]
            all_results = explicit_dicts + semantic_dicts
            
            # Generate context
            context = self._generate_context(all_results)

            # If we have a thread, add the message to it
            if thread_id:
                try:
                    thread = await self.get_thread(thread_id, user_id)
                    if thread:
                        await self.add_message(thread_id, "user", content)
                except Exception as e:
                    logger.warning(f"Non-critical error handling thread: {e}")
                    # Continue even if thread operations fail
                    pass

            # Prepare messages for AI
            messages = [
                {
                    "role": "system",
                    "content": f"""{settings.SYSTEM_PROMPT}

MEMORY CONTEXT:
{user_settings['memory']}

ABOUT THE USER:
{user_settings['personal_info']}

Here are the relevant notes and their context:

{context}"""
                },
                {
                    "role": "user",
                    "content": content
                }
            ]

            # Get streaming AI response
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
            
            full_response = ""
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    content_delta = chunk.choices[0].delta.content
                    full_response += content_delta
                    yield ChatResponse(
                        content=content_delta,
                        sources=all_results,
                        thread_id=thread_id,
                        done=False
                    )
            
            # If we have a thread, add the AI response to it
            if thread_id:
                try:
                    thread = await self.get_thread(thread_id, user_id)
                    if thread:
                        await self.add_message(
                            thread_id,
                            "assistant",
                            full_response,
                            sources=all_results
                        )
                except Exception as e:
                    logger.warning(f"Non-critical error handling thread: {e}")
                    # Continue even if thread operations fail
                    pass
            
            # Send final message indicating completion
            yield ChatResponse(
                content="",
                sources=all_results,
                thread_id=thread_id,
                done=True
            )

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process message: {str(e)}"
            ) 