import asyncio
import streamlit as st
from typing import List, Optional, Callable
from datetime import datetime
import uuid
import json
from pathlib import Path
from openai import OpenAI

from src.types import Message, ChatThread, ThreadStorage
from src.settings import DEFAULT_SETTINGS, ChatSidebarSettings
from src.services.search_service import SearchService
from src.embedding_helper import generate_embedding
from src.generate_embeddings import generate_embeddings_for_directory

def load_css():
    """Load custom CSS styles."""
    css_path = Path(__file__).parent / 'styles' / 'main.css'
    with open(css_path) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

def count_indexed_files() -> int:
    """Count the number of indexed files in the embeddings directory."""
    embeddings_dir = Path("adil-clone/embeddings")
    return len(list(embeddings_dir.glob("*.json")))

class ChatSidebarView:
    """Streamlit-based chat interface implementation."""
    
    def __init__(self):
        """Initialize the chat view."""
        # Load custom CSS
        load_css()
        
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
            
        # Initialize search service
        self.search_service = SearchService(
            vault=DummyVault(),
            metadata_cache=DummyMetadataCache(),
            api_key=st.session_state.settings['openai_api_key']
        )

    def render(self):
        """Render the main chat interface."""
        st.title("Big Brain Chat")
        
        # Create persistent containers for status messages
        if 'status_container' not in st.session_state:
            st.session_state.status_container = st.empty()
        
        # Show indexed files count
        indexed_count = count_indexed_files()
        st.session_state.status_container.success(f"{indexed_count} files have already been successfully indexed.")

        # Rest of the UI
        with st.sidebar:
            self._render_settings()
            self._render_thread_list()
            self._render_index_button()
        
        self._render_chat_area()

    def _render_settings(self):
        """Render settings in the sidebar."""
        st.sidebar.header("Settings")
        
        # API Key input (showing stored key from secrets)
        api_key = st.sidebar.text_input(
            "OpenAI API Key",
            value=st.secrets.get('OPENAI_API_KEY', ''),
            type="password",
            disabled=True  # Make it read-only since it's from secrets
        )
        
        # Personal info
        # personal_info = st.sidebar.text_area(
        #     "About you",
        #     value=st.session_state.settings['personal_info']
        # )
        # if personal_info != st.session_state.settings['personal_info']:
        #     st.session_state.settings['personal_info'] = personal_info

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

    def _render_index_button(self):
        """Render the index button in the sidebar."""
        st.sidebar.header("Index Data")
        
        # Show total indexed files count in sidebar
        indexed_count = count_indexed_files()
        st.sidebar.caption(f"Total files indexed: {indexed_count}")
        
        # Create a placeholder for the status in the main area
        status_placeholder = st.empty()
        
        if st.sidebar.button("Index"):
            with status_placeholder:
                try:
                    with st.spinner("Indexing files..."):
                        # Run the indexing synchronously
                        result = asyncio.run(generate_embeddings_for_directory(
                            progress_callback=lambda x, total: st.write(f"Processing file {x} out of {total}...")
                        ))
                        
                        if result > 0:
                            st.success(f"Successfully indexed {result} new files!")
                        else:
                            st.info("No new files to index.")
                except Exception as e:
                    st.error(f"Error indexing files: {str(e)}")

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
            
            # Display sources in an expander below the message
            if message.role == "assistant" and message.sources:
                with st.expander("🔍 View Sources", expanded=False):
                    for result in message.sources:
                        source_name = Path(result['id']).name
                        st.write(f"- **{source_name}** (relevance: {result['score']:.2f})")
        
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
        api_key = st.secrets.get('OPENAI_API_KEY')
        if not api_key:
            st.error("OpenAI API key not found in secrets.")
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
            # Show searching status
            status_message.info("🔍 Searching through relevant documents...")
            search_results = await self.search_service.search(content)
            
            # Show context generation status
            status_message.info("📝 Generating context from search results...")
            context = self._generate_context(search_results)
            
            # Show message preparation status
            status_message.info("🤔 Preparing messages for AI response...")
            messages = [
                {"role": "system", "content": st.session_state.settings['system_prompt']},
                {"role": "system", "content": f"User's personal info: {st.session_state.settings['personal_info']}"},
                {"role": "system", "content": f"Context from notes:\n{context}"},
            ]
            
            # Add conversation history
            for msg in st.session_state.current_thread.messages[:-1]:
                messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": content})
            
            # Show AI thinking status
            status_message.info("🧠 Generating AI response...")
            
            # Get AI response
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=st.session_state.settings['model'],
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                stream=True  # Enable streaming
            )
            
            # Clear status message before showing response
            status_message.empty()
            
            # Create placeholder for streaming response
            message_placeholder = st.empty()
            full_response = ""
            
            # Stream the response
            with st.chat_message("assistant"):
                for chunk in response:
                    if chunk.choices[0].delta.content is not None:
                        full_response += chunk.choices[0].delta.content
                        message_placeholder.markdown(full_response + "▌")
                message_placeholder.markdown(full_response)
            
            # Store response and sources in session state
            assistant_message = Message(
                role="assistant",
                content=full_response,
                timestamp=datetime.now(),
                sources=search_results  # Add sources to the message
            )
            st.session_state.current_thread.messages.append(assistant_message)
            
            # Update thread title if first exchange
            if len(st.session_state.current_thread.messages) == 2:
                st.session_state.current_thread.title = content[:30] + "..."
            
            st.rerun()
        except Exception as e:
            status_message.error(f"Error processing message: {str(e)}")

    def _generate_context(self, search_results: List[dict]) -> str:
        """Generate context string from search results."""
        print("\nGenerating context from search results:")
        context_parts = []
        for result in search_results:
            print(f"- Including content from {result['id']} (score: {result['score']})")
            context_parts.append(f"From [[{result['id']}]]:\n{result['content']}\n")
        
        context = "\n".join(context_parts)
        print(f"\nGenerated context length: {len(context)} characters")
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
        page_title="My Big Brain Chat",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    view = ChatSidebarView()
    view.render()

if __name__ == "__main__":
    main() 