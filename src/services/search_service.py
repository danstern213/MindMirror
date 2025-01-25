from typing import List, Optional, TypedDict
import streamlit as st
from pathlib import Path
from supabase import create_client, Client
import json  # Add this import at the top

# Change relative imports to absolute imports
from src.embedding_helper import generate_embedding
from src.storage_service import get_all_embeddings

# Add stub classes for Obsidian types if needed
class VaultFile:
    """Stub class for Obsidian's TFile."""
    def __init__(self, path: str):
        self.path = path
        self.basename = path.split('/')[-1]

class SearchResult(TypedDict):
    id: str
    score: float
    content: str
    full_content: Optional[str]
    keyword_score: Optional[float]
    matched_keywords: Optional[List[str]]

class SearchService:
    def __init__(self, vault, metadata_cache, api_key: str = None):
        """Keep the original constructor as other parts of the app expect it"""
        self.vault = vault
        self.metadata_cache = metadata_cache
        self.api_key = api_key or st.secrets.get('OPENAI_API_KEY')
        self.supabase: Client = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_KEY"]
        )
    
    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        try:
            # Convert vectors to float if they aren't already
            vec_a = [float(a) for a in vec_a]
            vec_b = [float(b) for b in vec_b]
            
            dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
            magnitude_a = (sum(a * a for a in vec_a)) ** 0.5
            magnitude_b = (sum(b * b for b in vec_b)) ** 0.5
            
            if magnitude_a == 0 or magnitude_b == 0:
                return 0.0
            
            return dot_product / (magnitude_a * magnitude_b)
        except Exception as e:
            print(f"Error in cosine similarity calculation: {e}")
            print(f"Vector A type: {type(vec_a)}, length: {len(vec_a)}")
            print(f"Vector B type: {type(vec_b)}, length: {len(vec_b)}")
            return 0.0
    
    async def perform_semantic_search(self, query: str) -> List[SearchResult]:
        """Perform semantic search using embeddings."""
        print("\n=== Starting Semantic Search ===")
        
        # Generate query embedding
        query_embedding = generate_embedding(query, self.api_key)
        
        try:
            # Get embeddings and file info in one query
            response = self.supabase.table('embeddings')\
                .select('*, files!inner(title)')\
                .execute()
            
            if hasattr(response, 'error') and response.error:
                print(f"Error fetching embeddings: {response.error}")
                return []
            
            embeddings = [
                {
                    'id': item['file_id'],
                    'embedding': json.loads(item['embedding']) if isinstance(item['embedding'], str) else item['embedding'],
                    'text': item['text'],
                    'title': item['files']['title']  # Include the title from the join
                } 
                for item in response.data
            ]
            print(f"Found {len(embeddings)} embeddings")

            # Add debug info
            if response.data:
                print("\nDebug - First document:")
                print(f"Title: {response.data[0]['files']['title']}")
                print(f"Text length: {len(response.data[0]['text'])}")
                print(f"First 100 chars: {response.data[0]['text'][100:]}")
        except Exception as e:
            print(f"Error fetching embeddings from Supabase: {e}")
            print(f"First embedding format: {type(response.data[0]['embedding']) if response.data else 'No data'}")
            return []

        results: List[SearchResult] = []
        similarity_threshold = 0.7
        highly_relevant_threshold = 0.8

        # Group results by file_id
        grouped_results = {}
        for doc in embeddings:
            score = self.cosine_similarity(query_embedding, doc['embedding'])
            if score >= similarity_threshold:
                doc_id = doc['id']
                if doc_id not in grouped_results:
                    grouped_results[doc_id] = {
                        'id': doc_id,
                        'score': score,
                        'chunks': [],
                        'title': doc['title']
                    }
                grouped_results[doc_id]['chunks'].append({
                    'text': doc['text'],
                    'score': score
                })
        
        # Combine chunks and sort by relevance
        for doc_id, data in grouped_results.items():
            # Sort chunks by relevance
            sorted_chunks = sorted(data['chunks'], key=lambda x: x['score'], reverse=True)
            # Combine text from top chunks
            combined_text = '\n'.join(chunk['text'] for chunk in sorted_chunks[:3])
            results.append({
                'id': data['id'],
                'score': data['score'],
                'content': combined_text,
                'full_content': combined_text,
                'title': data['title']
            })

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
        """Extract a more comprehensive section of content."""
        # Return more content, or the full document if it's highly relevant
        return content[:2000] if len(content) > 2000 else content

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

        # Return results sorted by score
        return sorted(semantic_results, key=lambda x: x['score'], reverse=True)
