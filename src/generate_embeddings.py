from supabase import create_client, Client
import streamlit as st
from src.embedding_helper import generate_embedding
from typing import List

class EmbeddingService:
    def __init__(self):
        self.supabase: Client = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_KEY"]
        )

    def chunk_text(self, text: str, chunk_size: int = 2000, overlap: int = 200) -> List[str]:
        """Split text into overlapping chunks to maintain context."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            # Find a good break point
            if end < len(text):
                # Try to break at paragraph or sentence
                for separator in ['\n\n', '\n', '. ']:
                    pos = text[start:end].rfind(separator)
                    if pos != -1:
                        end = start + pos + len(separator)
                        break
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - overlap  # Create overlap with previous chunk
        return chunks

    def generate_and_save_embedding(self, text: str, file_id: str):
        """Generate embeddings for text chunks and save to Supabase."""
        try:
            # Split text into chunks and generate embeddings
            chunks = self.chunk_text(text)
            print(f"\nProcessing {len(chunks)} chunks for file {file_id}")

            # Save embeddings for each chunk
            for i, chunk in enumerate(chunks):
                try:
                    embedding = generate_embedding(chunk)
                    response = self.supabase.table('embeddings').insert({
                        'file_id': file_id,
                        'embedding': embedding,
                        'text': chunk,
                        'chunk_index': i
                    }).execute()

                    if hasattr(response, 'error') and response.error:
                        print(f"Error saving chunk {i}: {response.error}")
                    else:
                        print(f"Successfully saved chunk {i} for file {file_id}")
                except Exception as chunk_error:
                    print(f"Error processing chunk {i}: {chunk_error}")

        except Exception as e:
            print(f"An error occurred while generating or saving embeddings: {str(e)}")
            import traceback
            traceback.print_exc() 