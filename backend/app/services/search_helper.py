from typing import List, Optional
import math
from .embedding_helper import generate_embedding
from ..models.search import LinkedContext, SearchResult
from ..core.config import get_settings

settings = get_settings()

def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
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
        
        similarity = dot_product / (magnitude_a * magnitude_b)
        # Ensure score is between -1 and 1
        return max(min(similarity, 1.0), -1.0)
    except Exception as e:
        print(f"Error in cosine similarity calculation: {e}")
        return 0.0

def extract_keywords(text: str) -> List[str]:
    """Extract meaningful keywords from text."""
    import re
    # Use re.sub with a raw string pattern for proper escaping
    cleaned_text = re.sub(r'[^a-zA-Z0-9\s]', '', text.lower())
    words = cleaned_text.split()
    words = [word for word in words if len(word) > 2]
    
    stop_words = {
        'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 
        'but', 'in', 'to', 'for', 'with', 'by', 'from', 'up', 'about', 
        'into', 'over', 'after'
    }
    
    return [word for word in words if word not in stop_words]

def calculate_keyword_score(content: str, keywords: List[str]) -> float:
    """Calculate keyword-based relevance score."""
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

def extract_relevant_section(content: str, max_length: int = 2000) -> str:
    """Extract a more comprehensive section of content."""
    return content[:max_length] if len(content) > max_length else content

async def get_linked_contexts(
    content: str,
    query_embedding: List[float],
    api_key: Optional[str] = None,
    similarity_threshold: Optional[float] = None
) -> List[LinkedContext]:
    """Extract and process linked contexts from content."""
    import re
    link_regex = r'\[\[(.*?)\]\]'
    matches = re.finditer(link_regex, content)
    linked_contexts: List[LinkedContext] = []
    
    similarity_threshold = similarity_threshold or settings.SIMILARITY_THRESHOLD
    
    for match in matches:
        path = match.group(1).split('|')[0]  # Handle aliased links
        try:
            # Generate embedding for the linked content
            linked_embedding = generate_embedding(path, api_key)
            relevance = cosine_similarity(query_embedding, linked_embedding)
            
            if relevance >= similarity_threshold:
                linked_contexts.append(
                    LinkedContext(
                        note_path=path,
                        relevance=relevance,
                        context=extract_relevant_section(path)
                    )
                )
        except Exception as e:
            print(f"Error processing linked note {path}: {e}")
    
    return sorted(linked_contexts, key=lambda x: x.relevance, reverse=True) 