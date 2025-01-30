import asyncio
import streamlit as st
from typing import List, Optional, Callable
from datetime import datetime
import uuid
import time
import json
from pathlib import Path
from openai import OpenAI
import re
from supabase import create_client, Client

from src.types import Message, ChatThread, ThreadStorage
from src.settings import DEFAULT_SETTINGS, ChatSidebarSettings
from src.services.search_service import SearchService, SearchResult, VaultFile
from src.embedding_helper import generate_embedding, initialize_openai
from src.generate_embeddings import EmbeddingService
from src.services.upload_service import UploadService
from src.auth import Auth

class ChatSidebarView:
    """Streamlit-based chat interface implementation."""
    
    def __init__(self):
        """Initialize the chat view."""
        # Initialize auth
        self.auth = Auth()
        
        # Initialize settings with API key from secrets
        if 'settings' not in st.session_state:
            settings = DEFAULT_SETTINGS.copy()
            settings['openai_api_key'] = st.secrets.get('OPENAI_API_KEY', '')
            st.session_state.settings = settings
        
        # Initialize other state
        if 'threads' not in st.session_state:
            st.session_state.threads = []
        if 'current_thread' not in st.session_state:
            st.session_state.current_thread = None
        if 'embeddings_processed' not in st.session_state:
            st.session_state.embeddings_processed = 0
        if 'indexing_in_progress' not in st.session_state:
            st.session_state.indexing_in_progress = False
        
        # Initialize services
        self.supabase = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_KEY"]
        )
        self.search_service = SearchService(
            vault=DummyVault(),
            metadata_cache=DummyMetadataCache(),
            api_key=st.session_state.settings['openai_api_key']
        )
        self.upload_service = UploadService()
        self.embedding_service = EmbeddingService()

    def render(self):
        """Render the main chat interface."""
        # Render authentication first
        self.auth.render_auth()
        
        # Only show the main interface if user is authenticated
        if st.session_state.user:
            st.title("Big Brain Chat")
            
            # Show count of indexed files for current user
            indexed_count = self._count_user_files()
            if indexed_count > 0:
                st.success(f"{indexed_count} {'file has' if indexed_count == 1 else 'files have'} been indexed and are ready for search.")
            else:
                st.info("Upload files to begin searching through your documents.")

            # Rest of the UI
            with st.sidebar:
                self._render_settings()
                self._render_thread_list()
                self._render_upload_section()
            
            self._render_chat_area()

    def _count_user_files(self) -> int:
        """Count files uploaded by the current user."""
        try:
            response = self.supabase.table('files')\
                .select('id', count='exact')\
                .filter('user_id', 'eq', st.session_state.user.id)\
                .execute()
            
            return len(response.data) if response.data else 0
        except Exception as e:
            print(f"Error counting user files: {e}")
            return 0

    def _render_settings(self):
        """Render settings in the sidebar."""
        st.sidebar.header("Settings")
        
        # API Key input with default from secrets but allowing override
        api_key = st.sidebar.text_input(
            "OpenAI API Key",
            value=st.session_state.settings['openai_api_key'],
            type="password",
            disabled=False
        )
        
        # Update API key in session state and services if changed
        if api_key != st.session_state.settings['openai_api_key']:
            st.session_state.settings['openai_api_key'] = api_key
            # Update the search service with new key
            self.search_service.api_key = api_key
            # Initialize OpenAI client with new key
            initialize_openai(api_key)
            # Force a rerun to ensure all components update
            st.rerun()

        if st.button("Logout"):
            self.supabase.auth.sign_out()
            st.session_state.user = None
            st.rerun()

    def _render_thread_list(self):
        """Render thread list in sidebar."""
        st.sidebar.header("Conversations")
        
        # New thread button
        if st.sidebar.button("New Chat"):
            self._create_new_thread()
        
        # Thread list
        for thread in st.session_state.threads:
            if st.sidebar.button(
                thread.title,
                key=f"thread_{thread.id}",
                use_container_width=True
            ):
                st.session_state.current_thread = thread

    def _render_upload_section(self):
        """Render the file upload section with status."""
        st.sidebar.header("Document Management")
        
        # Initialize upload counter if not exists
        if 'upload_counter' not in st.session_state:
            st.session_state.upload_counter = 0
        
        # Persistent metrics at top
        indexed_count = self._count_user_files()
        st.sidebar.metric("Indexed Documents", indexed_count)
        
        # Check for OpenAI API key in both session state and secrets
        api_key = st.session_state.settings.get('openai_api_key') or st.secrets.get('OPENAI_API_KEY')
        if not api_key:
            st.sidebar.error("⚠️ Please enter your OpenAI API key in Settings before uploading files.")
            return
        
        # Status container for processing messages
        status_container = st.sidebar.empty()
        
        # File uploader with dynamic key
        uploaded_files = st.sidebar.file_uploader(
            "Upload Files",
            accept_multiple_files=True,
            help="Files will be automatically indexed after upload",
            key=f"file_uploader_{st.session_state.upload_counter}"
        )

        # Show reset button
        if st.sidebar.button("Clear and Upload More Files"):
            # Increment the counter to reset the uploader
            st.session_state.upload_counter += 1
            # Clear the status messages
            status_container.empty()
            # Rerun to refresh the uploader
            st.rerun()
        
        # Process files when uploaded
        if uploaded_files:
            total_files = len(uploaded_files)
            
            for i, uploaded_file in enumerate(uploaded_files, 1):
                status_container.info(f"Processing file {i} of {total_files}: {uploaded_file.name}")
                self.upload_service.save_file_to_supabase(uploaded_file)
            
            status_container.success(f"✅ Processed {total_files} files")
            
            

    def _render_chat_area(self):
        """Render main chat area."""
        # Check if there is a current thread
        if not st.session_state.current_thread:
            # Automatically create a new thread if none exists
            self._create_new_thread()
        
        # Display messages
        for message in st.session_state.current_thread.messages:
            # Display the message content
            with st.chat_message(message.role):
                st.markdown(message.content)
                
                # Only show sources for completed assistant messages
                if message.role == "assistant" and message.sources and message == st.session_state.current_thread.messages[-1]:
                    with st.expander("🔍 View Sources", expanded=False):
                        for result in message.sources:
                            st.write(f"- **{result['title']}** (relevance: {result['score']:.2f})")
        
        # Input area
        if prompt := st.chat_input("Type your message..."):
            asyncio.run(self._handle_user_message(prompt))

    def _create_new_thread(self):
        """Create a new chat thread."""
        thread = ChatThread(
            id=str(uuid.uuid4()),
            title="New Chat",
            messages=[],
            created=datetime.now(),
            last_updated=datetime.now()
        )
        st.session_state.threads.append(thread)
        st.session_state.current_thread = thread
        st.rerun()

    async def _handle_user_message(self, content: str):
        """Handle incoming user message."""
        # Get API key from session state first, then fall back to secrets
        api_key = st.session_state.settings.get('openai_api_key') or st.secrets.get('OPENAI_API_KEY')
        if not api_key:
            st.error("OpenAI API key not found. Please enter your API key in the settings.")
            return
        
        # Create a status message placeholder
        status_message = st.empty()
        
        # Add and display user message immediately
        user_message = Message(
            role="user",
            content=content,
            timestamp=datetime.now()
        )
        st.session_state.current_thread.messages.append(user_message)
        
        # Display the message
        with st.chat_message("user"):
            st.write(content)
        
        try:
            # First, analyze conversation continuity
            conversation_analysis = await self.analyze_conversation_continuity(content, status_message)
            
            # Show searching status
            status_message.info("🔍 Searching through relevant documents...")
            
            # Get explicitly referenced notes first
            explicit_results = await self.get_explicitly_referenced_notes(content)
            
            # Then get semantic search results
            semantic_results = await self.search_service.search(conversation_analysis['search_query'])
            
            # Merge results, prioritizing explicit references
            search_results = [
                *explicit_results,
                *[result for result in semantic_results 
                  if result['score'] > 0.75 and 
                  not any(explicit['id'] == result['id'] for explicit in explicit_results)]
            ]
            
            # Show context generation status
            status_message.info("📝 Generating context from search results...")
            context = self._generate_context(search_results)
            
            # Show message preparation status
            status_message.info("🤔 Preparing messages for AI response...")
            
            # Create system prompt with conversation analysis
            system_prompt = f"""{st.session_state.settings['system_prompt']}

MEMORY CONTEXT:
{st.session_state.settings.get('memory', '')}

ABOUT THE USER:
{st.session_state.settings['personal_info']}

Conversation Analysis:
{"This is a follow-up question to the previous topic. Consider the previous context while maintaining focus on new information." if conversation_analysis['is_follow_up'] else "This is a new topic. Focus on providing fresh information without being constrained by the previous conversation."}

Current conversation context:
{chr(10).join(f"{msg.role}: {msg.content}" for msg in st.session_state.current_thread.messages[-3:])}

I am providing you with both relevant sections and their surrounding context from the user's notes. Each note is marked with its relevance score (higher is better).

Remember to:
1. {"Build upon the previous conversation while incorporating new information from the notes" if conversation_analysis['is_follow_up'] else "Focus on the new topic without being constrained by the previous conversation"}
2. Look for new connections in the provided notes
3. When referencing notes, always use the double bracket format: [[note name]]

Here are the relevant notes:

{context}"""

            messages = [
                {
                    "role": "system",
                    "content": """You are a helpful AI assistant. When referencing documents, use their titles in double square brackets like this: [[Title]].
                    Available documents and their titles:
                    {}
                    
                    IMPORTANT: Always use the exact titles shown above when referencing documents. Never use IDs or modify the titles.
                    """.format('\n'.join([f"- [[{result['title']}]]" for result in search_results]))
                },
                {
                    "role": "user",
                    "content": f"Context from relevant documents:\n{context}\n\nUser question: {content}"
                }
            ]
            
            # Add any conversation history if it's a follow-up
            if conversation_analysis['is_follow_up']:
                # Insert previous messages before the new ones
                messages[1:1] = [
                    {"role": msg.role, "content": msg.content}
                    for msg in st.session_state.current_thread.messages[-1:]  # Last 2 messages
                ]

            # Show AI thinking status
            status_message.info("🧠 Generating AI response...")
            
            # Get AI response using the API key from session state
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=st.session_state.settings['model'],
                messages=messages,
                temperature=0.7,
                max_tokens=4000,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                stream=True
            )
            
            # Clear status message before showing response
            status_message.empty()
            
            # Create placeholder for streaming response
            message_placeholder = st.empty()
            full_response = ""
            
            # Stream the response
            with st.chat_message("assistant"):
                try:
                    # Create a container for the message and sources
                    message_container = st.container()
                    
                    # Stream the response in the message container
                    with message_container:
                        message_placeholder = st.empty()
                        chunk_count = 0
                        for chunk in response:
                            if chunk.choices[0].delta.content is not None:
                                full_response += chunk.choices[0].delta.content
                                message_placeholder.markdown(full_response + "▌")
                                chunk_count += 1
                        # Final render of the complete response without cursor
                        print(f"Response complete. Total chunks: {chunk_count}, Response length: {len(full_response)}")
                        message_placeholder.markdown(full_response)
                    
                    # Store response and sources in session state
                    assistant_message = Message(
                        role="assistant",
                        content=full_response,
                        timestamp=datetime.now(),
                        sources=search_results
                    )
                    st.session_state.current_thread.messages.append(assistant_message)
                    
                    # Update thread title if first exchange
                    if len(st.session_state.current_thread.messages) == 2:
                        st.session_state.current_thread.title = content[:30] + "..."
                    
                    # Add a longer delay to ensure UI updates
                    await asyncio.sleep(0.5)
                    
                    # Only show sources after response is complete and rendered
                    if search_results:
                        with st.expander("🔍 View Sources", expanded=False):
                            for result in search_results:
                                st.write(f"- **{result['title']}** (relevance: {result['score']:.2f})")
                finally:
                    print("Triggering rerun...")
                    # Only rerun after everything is complete
                    st.rerun()
        except Exception as e:
            status_message.error(f"Error processing message: {str(e)}")

    async def get_explicitly_referenced_notes(self, message: str) -> List[SearchResult]:
        """Extract and process explicitly referenced notes from the message."""
        link_regex = r'\[\[(.*?)\]\]'
        matches = re.finditer(link_regex, message)
        results = []

        for match in matches:
            path = match.group(1)
            file = self.vault.get_abstract_file_by_path(path)
            
            if file:
                try:
                    content = await self.vault.read(file)
                    results.append({
                        'id': file.path,
                        'score': 1.0,  # Maximum relevance for explicit references
                        'content': content,
                        'explicit': True,
                        'matched_keywords': [],
                        'linked_contexts': []
                    })
                except Exception as error:
                    print(f"Error reading file {path}: {error}")

        return results

    async def analyze_conversation_continuity(self, message: str, status_message) -> dict:
        """Analyze if the new message is a follow-up to previous conversation."""
        # If no previous conversation, it's not a follow-up
        if len(st.session_state.current_thread.messages) < 2:
            return {
                'is_follow_up': False,
                'search_query': message,
                'context': message
            }

        # Get last exchange
        messages = st.session_state.current_thread.messages
        last_user_message = next(msg for msg in reversed(messages[:-1]) if msg.role == 'user')
        last_assistant_message = next(msg for msg in reversed(messages[:-1]) if msg.role == 'assistant')

        try:
            status_message.info('Analyzing conversation context...')
            
            client = OpenAI(api_key=st.secrets.get('OPENAI_API_KEY'))
            response = client.chat.completions.create(
                model="gpt-4-0125-preview",
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
                    {"role": "user", "content": last_user_message.content},
                    {"role": "assistant", "content": last_assistant_message.content},
                    {"role": "user", "content": message}
                ],
                temperature=0.1
            )

            analysis = json.loads(response.choices[0].message.content)
            
            return {
                'is_follow_up': analysis['isFollowUp'],
                'search_query': analysis['searchQuery'],
                'context': f"{last_user_message.content}\n{last_assistant_message.content}\n{message}" if analysis['isFollowUp'] else message
            }
        except Exception as error:
            print(f"Error analyzing conversation continuity: {error}")
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

    def save_threads(self):
        """Save threads to disk."""
        storage = ThreadStorage(
            version=1,
            threads=st.session_state.threads
        )
        # TODO: Implement actual file saving
        pass

    def load_threads(self):
        """Load threads from disk."""
        # TODO: Implement actual file loading
        pass

class DummyVault:
    """Simple file reader for testing."""
    def get_abstract_file_by_path(self, path: str):
        """Get file by path."""
        # Remove the absolute path prefix to get relative path
        if "data_7_7_24" in path:
            parts = path.split("data_7_7_24")
            path = f"data_7_7_24{parts[1]}"
        return VaultFile(path)
    
    async def read(self, file: 'VaultFile') -> str:
        """Read file content."""
        try:
            with open(file.path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading file {file.path}: {e}")
            return ""
    
    def get_markdown_files(self):
        return []

class VaultFile:
    """Simple file wrapper."""
    def __init__(self, path: str):
        self.path = path
        self.basename = path.split('/')[-1]

class DummyMetadataCache:
    """Stub class for testing without Obsidian's MetadataCache."""
    def get_file_cache(self, file):
        return {'links': []}

def main():
    """Main entry point for Streamlit app."""
    st.set_page_config(
        page_title="Big Brain Chat",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            'About': 'Big Brain Chat Application'
        }
    )
    view = ChatSidebarView()
    view.render()

if __name__ == "__main__":
    main() 