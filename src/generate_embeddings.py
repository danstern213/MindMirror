import os
from pathlib import Path
import asyncio
from typing import List
import streamlit as st

from src.embedding_helper import generate_embedding
from src.storage_service import save_embedding, Embedding

async def process_file(file_path: Path) -> Embedding:
    """Process a single file and generate its embedding."""
    try:
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"Processing file: {file_path}")
        
        # Generate embedding
        embedding = generate_embedding(
            content,
            st.secrets.get('OPENAI_API_KEY')
        )
        
        print(f"Successfully embedded: {file_path}")
        
        return {
            'id': str(file_path),
            'embedding': embedding,
            'last_modified': file_path.stat().st_mtime
        }
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None

async def generate_embeddings_for_directory(
    directory: str = "data_7_7_24",
    progress_callback = None
) -> int:
    """Generate embeddings for first 100 files in directory."""
    data_dir = Path(directory).resolve()  # Get absolute path
    print(f"\nLooking for files in: {data_dir}")
    
    if not data_dir.exists():
        print(f"Directory not found: {data_dir}")
        raise ValueError(f"Directory not found: {data_dir}")

    # Get first 100 files
    files = [
        f for f in data_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in ['.txt', '.md', '.json', '.csv']
    ][:100]  # Limit to first 100 files
    
    print(f"\nFound {len(files)} files to process")
    print("File list:")
    for f in files:
        print(f"- {f}")
    
    processed = 0
    for file in files:
        print(f"\nStarting file {processed + 1}/{len(files)}: {file}")
        embedding = await process_file(file)
        if embedding:
            await save_embedding(embedding)
            processed += 1
            print(f"Successfully saved embedding for: {file}")
            if progress_callback:
                progress_callback(processed)
        else:
            print(f"Failed to process: {file}")
    
    print(f"\nFinished processing. Successfully embedded {processed} files.")
    return processed 