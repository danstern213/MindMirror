import os
from pathlib import Path
import asyncio
from typing import List
import streamlit as st
import json

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
    directory: str = "data_1_7_25",
    progress_callback = None
) -> int:
    """Generate embeddings for files in directory, skipping already processed files."""
    data_dir = Path(directory).resolve()
    print(f"\nLooking for files in: {data_dir}")
    
    if not data_dir.exists():
        raise ValueError(f"Directory not found: {data_dir}")

    # Get files
    files = [
        f for f in data_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in ['.txt', '.md', '.json', '.csv']
    ] # if needed to debug, limit to 120 files ; [:120]
    
    total_files = len(files)
    processed = 0
    
    for file in files:
        # Call progress callback immediately with total files count
        if progress_callback:
            progress_callback(processed, total_files)
            
        # Check if embedding exists
        embedding_file = Path(f"adil-clone/embeddings/{file.stem}.json")
        if embedding_file.exists():
            print(f"Skipping {file} as it is already processed.")
            continue

        print(f"\nStarting file {processed + 1}/{total_files}: {file}")
        embedding = await process_file(file)
        if embedding:
            await save_embedding(embedding)
            processed += 1
            print(f"Successfully saved embedding for: {file}")
    
    # Call progress callback one final time
    if progress_callback:
        progress_callback(processed, total_files)
    
    return processed 