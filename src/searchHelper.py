from typing import List, Dict, Optional, TypedDict
from dataclasses import dataclass
import math
from .embedding_helper import generate_embedding
from .storage_service import get_all_embeddings, Embedding

@dataclass
class LinkedContext:
    note_path: str
    relevance: float
    context: str

class SearchResult(TypedDict):
    id: str
    score: float
    content: str
    explicit: Optional[bool]
    full_content: Optional[str]
    linked_contexts: Optional[List[LinkedContext]]

def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    magnitude_a = math.sqrt(sum(a * a for a in vec_a))
    magnitude_b = math.sqrt(sum(b * b for b in vec_b))
    similarity = dot_product / (magnitude_a * magnitude_b)
    return max(min(similarity, 1), -1)

class VaultFile:
    """Stub class to represent Obsidian's TFile."""
    def __init__(self, path: str):
        self.path = path

class Vault:
    """Stub class to represent Obsidian's Vault."""
    async def read(self, file: VaultFile) -> str:
        """Placeholder for reading file content."""
        # In real implementation, this would read from your file system
        raise NotImplementedError("Implement file reading logic")

    def get_abstract_file_by_path(self, path: str) -> Optional[VaultFile]:
        """Placeholder for getting file by path."""
        return VaultFile(path)

async def get_linked_notes(content: str, vault: Vault) -> List[VaultFile]:
    """Extract linked notes from content using wiki-link format."""
    import re
    link_regex = r'\[\[(.*?)\]\]'
    linked_files = []
    matches = re.finditer(link_regex, content)
    
    for match in matches:
        path = match.group(1).split('|')[0]  # Handle aliased links
        file = vault.get_abstract_file_by_path(path)
        if file:
            linked_files.append(file)
    
    return linked_files

async def get_relevant_linked_context(
    query_embedding: List[float],
    linked_file: VaultFile,
    vault: Vault,
    api_key: str,
    similarity_threshold: float = 0.75
) -> Optional[LinkedContext]:
    """Get relevant context from linked notes."""
    try:
        content = await vault.read(linked_file)
        chunks = split_into_chunks(content, 500)
        chunk_embeddings = [
            await generate_embedding(chunk, api_key)
            for chunk in chunks
        ]
        
        # Find the most relevant chunk
        chunk_scores = [
            cosine_similarity(query_embedding, emb)
            for emb in chunk_embeddings
        ]
        best_score = max(chunk_scores)
        
        if best_score >= similarity_threshold:
            best_chunk_index = chunk_scores.index(best_score)
            return LinkedContext(
                note_path=linked_file.path,
                relevance=best_score,
                context=chunks[best_chunk_index]
            )
    except Exception as error:
        print(f"Error processing linked note {linked_file.path}:", error)
    
    return None

async def semantic_search(
    query: str,
    api_key: str,
    vault: Vault,
    top_k: int = 3,
    on_progress = None
) -> List[SearchResult]:
    """Perform semantic search across notes."""
    query_embedding = await generate_embedding(query, api_key)
    embeddings = await get_all_embeddings()
    results: List[SearchResult] = []
    similarity_threshold = 0.80
    
    for doc in embeddings:
        if on_progress:
            on_progress(doc.id)
        
        score = cosine_similarity(query_embedding, doc.embedding)
        
        if score >= similarity_threshold:
            file = vault.get_abstract_file_by_path(doc.id)
            
            if file:
                try:
                    content = await vault.read(file)
                    
                    # Process main content
                    chunks = split_into_chunks(content, 500)
                    chunk_embeddings = [
                        await generate_embedding(chunk, api_key)
                        for chunk in chunks
                    ]
                    chunk_scores = [
                        cosine_similarity(query_embedding, emb)
                        for emb in chunk_embeddings
                    ]
                    best_chunk_index = chunk_scores.index(max(chunk_scores))
                    
                    # Get linked notes
                    linked_files = await get_linked_notes(content, vault)
                    linked_contexts: List[LinkedContext] = []
                    
                    # Process each linked note
                    for linked_file in linked_files:
                        linked_context = await get_relevant_linked_context(
                            query_embedding,
                            linked_file,
                            vault,
                            api_key
                        )
                        
                        if linked_context:
                            linked_contexts.append(linked_context)
                    
                    # Sort linked contexts by relevance
                    linked_contexts.sort(key=lambda x: x.relevance, reverse=True)
                    
                    results.append({
                        'id': doc.id,
                        'score': score,
                        'content': chunks[best_chunk_index],
                        'full_content': content,
                        'linked_contexts': linked_contexts[:3]  # Top 3 most relevant
                    })
                except Exception as error:
                    print(f"Error reading file {doc.id}:", error)
    
    return sorted(
        results,
        key=lambda x: x['score'],
        reverse=True
    )[:top_k]

def split_into_chunks(text: str, chunk_size: int) -> List[str]:
    """Split text into chunks of approximately equal size."""
    chunks: List[str] = []
    sentences = text.split(r'[.!?]+')
    current_chunk = ''
    
    for sentence in sentences:
        if len(current_chunk + sentence) > chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            current_chunk += (' ' if current_chunk else '') + sentence
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks 