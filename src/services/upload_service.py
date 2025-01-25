from supabase import create_client, Client
import streamlit as st
import re
from src.generate_embeddings import EmbeddingService

class UploadService:
    def __init__(self):
        self.supabase: Client = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_KEY"]
        )
        self.embedding_service = EmbeddingService()

    def save_file_to_supabase(self, uploaded_file):
        """Save file to Supabase and generate embeddings."""
        try:
            # Read file content
            file_content = uploaded_file.read()
            file_name = uploaded_file.name

            # Sanitize file name
            sanitized_file_name = re.sub(r'[^\w\-_\. ]', '_', file_name)

            # Upload to Supabase storage
            storage_response = self.supabase.storage.from_('documents').upload(sanitized_file_name, file_content)

            if hasattr(storage_response, 'error') and storage_response.error:
                st.error(f"Error uploading {sanitized_file_name}: {storage_response.error['message']}")
                return

            # Save file metadata to files table
            file_response = self.supabase.table('files').insert({
                'filename': file_name,
                'storage_path': sanitized_file_name,
                'title': file_name,
                'status': 'pending_embedding'
            }).execute()

            if hasattr(file_response, 'error') and file_response.error:
                st.error(f"Error saving file metadata: {file_response.error['message']}")
                return

            # Get the file ID
            file_id = file_response.data[0]['id']

            # Generate and save embeddings
            content = file_content.decode('utf-8')  # Convert bytes to string
            self.embedding_service.generate_and_save_embedding(content, file_id)

            # Update file status to 'indexed'
            self.supabase.table('files').update({
                'status': 'indexed'
            }).eq('id', file_id).execute()

            st.success(f"Successfully uploaded and indexed {file_name}")
            
            return file_id

        except Exception as e:
            st.error(f"An error occurred while processing {uploaded_file.name}: {str(e)}")
            return None

    def fetch_documents_from_supabase(self):
        """Fetch the list of documents from Supabase files table."""
        response = self.supabase.table('files').select('*').execute()
        if hasattr(response, 'error') and response.error:
            raise Exception(f"Error fetching documents: {response.error['message']}")
        return response.data  # Returns list of file records with id, title, and storage_path

    def download_document_content(self, storage_path):
        """Download the content of a document from Supabase storage."""
        response = self.supabase.storage.from_('documents').download(storage_path)
        if hasattr(response, 'error') and response.error:
            raise Exception(f"Error downloading document {storage_path}: {response.error['message']}")
        return response.decode('utf-8') 