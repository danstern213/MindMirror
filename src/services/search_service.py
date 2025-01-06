from typing import List, Optional, TypedDict
from dataclasses import dataclass
import streamlit as st
from pathlib import Path

# Change relative imports to absolute imports
from src.embedding_helper import generate_embedding
from src.storage_service import get_all_embeddings

# Add stub classes for Obsidian types if needed
class VaultFile:
    """Stub class for Obsidian's TFile."""
    def __init__(self, path: str):
        self.path = path
        self.basename = path.split('/')[-1]

class MetadataCache:
    """Stub class for Obsidian's MetadataCache."""
    def get_file_cache(self, file: VaultFile) -> Optional[dict]:
        """Get metadata cache for a file."""
        # In real implementation, this would return file metadata
        return {'links': []}

@dataclass
class LinkedContext:
    note_path: str
    relevance: float
    context: str
    link_distance: int

class SearchResult(TypedDict):
    id: str
    score: float
    content: str
    explicit: Optional[bool]
    full_content: Optional[str]
    linked_contexts: Optional[List[LinkedContext]]
    keyword_score: Optional[float]
    link_score: Optional[float]
    matched_keywords: Optional[List[str]]
    link_path: Optional[List[str]]

class SearchService:
    def __init__(self, vault, metadata_cache, api_key: str = None):
        """
        Initialize SearchService.
        
        Args:
            vault: Stub for Obsidian's Vault
            metadata_cache: Stub for Obsidian's MetadataCache
            api_key: Optional OpenAI API key (will use secrets if not provided)
        """
        self.vault = vault
        self.metadata_cache = metadata_cache
        self.api_key = api_key or st.secrets.get('OPENAI_API_KEY')
    
    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = sum(a * a for a in vec_a) ** 0.5
        magnitude_b = sum(b * b for b in vec_b) ** 0.5
        return dot_product / (magnitude_a * magnitude_b)
    
    async def perform_semantic_search(self, query: str) -> List[SearchResult]:
        """Perform semantic search using embeddings."""
        print("\n=== Starting Semantic Search ===")
        print(f"Looking for embeddings in: {Path('adil-clone/embeddings').absolute()}")
        
        # Get stored embeddings
        embeddings = await get_all_embeddings()
        print(f"Found {len(embeddings)} embeddings")
        
        # Print first few embeddings for verification
        if embeddings:
            print("\nFirst few embeddings found:")
            for i, doc in enumerate(embeddings[:3]):
                print(f"- {doc['id']}")
                print(f"  Embedding length: {len(doc['embedding'])}")
        else:
            print("WARNING: No embeddings found!")
            return []

        # Generate query embedding
        query_embedding = generate_embedding(query, self.api_key)
        results: List[SearchResult] = []
        similarity_threshold = 0.775

        for doc in embeddings:
            score = self.cosine_similarity(query_embedding, doc['embedding'])
            if score >= similarity_threshold:
                print(f"\nMatch found: {doc['id']} (score: {score:.3f})")
                file = self.vault.get_abstract_file_by_path(doc['id'])
                if file:
                    try:
                        content = await self.vault.read(file)
                        results.append({
                            'id': doc['id'],
                            'score': score,
                            'content': self.extract_relevant_section(content),
                            'full_content': content
                        })
                        print(f"Successfully read content from {doc['id']}")
                    except Exception as error:
                        print(f"Error reading file {doc['id']}: {error}")

        print(f"\nFound {len(results)} results above threshold {similarity_threshold}")
        return sorted(results, key=lambda x: x['score'], reverse=True)[:50] ### this is where we limit the results

    def extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text."""
        words = text.lower().replace('[^a-zA-Z0-9\s]', '').split()
        words = [word for word in words if len(word) > 2]
        
        stop_words = {
            'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 
            'but', 'in', 'to', 'for', 'with', 'by', 'from', 'up', 'about', 
            'into', 'over', 'after'
        }
        
        return [word for word in words if word not in stop_words]

    def calculate_keyword_score(self, content: str, keywords: List[str]) -> float:
        """Calculate keyword-based relevance score.
        
        Args:
            content: The text content to analyze.
            keywords: List of keywords to search for.
            
        Returns:
            Normalized score based on keyword matches.
        """
        import re
        score = 0
        content_lower = content.lower()
        
        for keyword in keywords:
            # Use word boundaries to match whole words only
            pattern = fr'\b{re.escape(keyword)}\b'
            matches = re.findall(pattern, content_lower)
            if matches:
                score += len(matches)

        # Normalize score by content length (per 100 characters)
        return score / (len(content) / 100)

    def extract_relevant_section(self, content: str) -> str:
        """Extract the most relevant section of content."""
        return content[:500]

    async def search(self, query: str) -> List[SearchResult]:
        """
        Perform comprehensive search combining semantic and keyword-based approaches.
        """
        semantic_results = await self.perform_semantic_search(query)
        keywords = self.extract_keywords(query)
        
        # Add keyword scores to semantic results
        for result in semantic_results:
            if result.get('full_content'):
                result['keyword_score'] = self.calculate_keyword_score(
                    result['full_content'],
                    keywords
                )
                result['matched_keywords'] = [
                    k for k in keywords 
                    if k.lower() in result['full_content'].lower()
                ]

        # Process linked notes
        final_results: List[SearchResult] = []
        for result in semantic_results:
            linked_contexts = await self.traverse_links(result)
            if linked_contexts:
                result['linked_contexts'] = linked_contexts
            final_results.append(result)

        return sorted(final_results, key=lambda x: x['score'], reverse=True)

    async def traverse_links(self, result: SearchResult) -> List[LinkedContext]:
        """Process linked notes to find relevant contexts.
        
        Args:
            result: The search result to process links for.
            
        Returns:
            List of LinkedContext objects for related documents.
        """
        linked_contexts: List[LinkedContext] = []
        processed_files = set()
        
        file = self.vault.get_abstract_file_by_path(result['id'])
        if not file:
            return linked_contexts

        file_cache = self.metadata_cache.get_file_cache(file)
        if not file_cache:
            return linked_contexts

        # Process forward links
        links = file_cache.get('links', [])
        for link in links:
            linked_file = self.vault.get_abstract_file_by_path(link['link'])
            if linked_file and linked_file.path not in processed_files:
                processed_files.add(linked_file.path)
                context = await self.process_linked_file(linked_file, result['score'])
                if context:
                    linked_contexts.append(context)

        # Process backlinks
        all_files = self.vault.get_markdown_files()
        for potential_source in all_files:
            source_cache = self.metadata_cache.get_file_cache(potential_source)
            if source_cache and source_cache.get('links'):
                has_link = any(
                    link['link'] == file.path or link['link'] == file.basename
                    for link in source_cache['links']
                )
                if has_link and potential_source.path not in processed_files:
                    processed_files.add(potential_source.path)
                    context = await self.process_linked_file(
                        potential_source,
                        result['score']
                    )
                    if context:
                        linked_contexts.append(context)

        return linked_contexts

    async def process_linked_file(self, file: VaultFile, parent_score: float) -> Optional[LinkedContext]:
        """Process a linked file to extract relevant context.
        
        Args:
            file: The linked file to process.
            parent_score: The relevance score of the parent document.
            
        Returns:
            LinkedContext object if successful, None if error occurs.
        """
        try:
            content = await self.vault.read(file)
            return LinkedContext(
                note_path=file.path,
                relevance=parent_score * 0.8,  # Decay factor of 0.8 for linked documents
                context=self.extract_relevant_section(content),
                link_distance=1
            )
        except Exception as error:
            print(f"Error processing linked file {file.path}:", error)
            return None

# Add stub classes for Obsidian types if needed
class VaultFile:
    """Stub class for Obsidian's TFile."""
    def __init__(self, path: str):
        self.path = path
        self.basename = path.split('/')[-1]

class MetadataCache:
    """Stub class for Obsidian's MetadataCache."""
    def get_file_cache(self, file: VaultFile) -> Optional[dict]:
        """Get metadata cache for a file."""
        # In real implementation, this would return file metadata
        return {'links': []} 