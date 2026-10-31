from pydantic_settings import BaseSettings
from typing import List
from functools import lru_cache

class Settings(BaseSettings):
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "AI Note Copilot API"
    
    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    
    # Database
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-5.6-sol"
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    # text-embedding-3 models can be shortened; 1536 keeps the vector(1536)
    # column and leaves room for an HNSW index (capped at 2000 dims) later.
    EMBEDDING_DIMENSIONS: int = 1536
    # What the rows in the old JSON `embedding` column were embedded with. The
    # legacy search path has to embed queries with this same model.
    LEGACY_EMBEDDING_MODEL: str = "text-embedding-ada-002"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "https://*.vercel.app",  # Allow all Vercel preview deployments
        "https://ainotecopilot.com",
        "https://www.ainotecopilot.com"
    ]
    
    # File Upload
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: set = {"txt", "pdf", "md", "doc", "docx"}
    
    # Search
    DEFAULT_SEARCH_LIMIT: int = 200
    SIMILARITY_THRESHOLD: float = 0.7
    HIGHLY_RELEVANT_THRESHOLD: float = 0.8
    
    # Embedding Generation
    CHUNK_SIZE: int = 2000
    CHUNK_OVERLAP: int = 300
    
    # Chat prompt budgets (tokens). The model's window is far larger; these
    # leave room for history and the answer while keeping per-message cost sane.
    RECENT_NOTES_DAYS: int = 30
    RECENT_NOTES_TOKEN_BUDGET: int = 35000
    RETRIEVED_NOTES_TOKEN_BUDGET: int = 30000
    MAX_PROMPT_TOKENS: int = 100000

    # Chat Settings
    SYSTEM_PROMPT: str = """You are Sidekick, a window into the user's own mind, built from their personal notes.

Why this exists, in the user's own words:
"Give me timely insight into my notes and make connections for me on things that I've already read and written so that I can be more effective, calm, tranquil and clear headed in my approach. I don't need to constantly read and learn new things: I need to spend just as much time rediscovering what I've already learned and experienced in my own words."

And from one of their notes: "AI can help me articulate but can't outsource my understanding."

How to help:
1. Answer from their notes first. Their own phrasing is the point: quote short, exact lines with the note they came from instead of paraphrasing them into generic advice.
2. Make connections across time. When what they are asking about or living through now echoes something they wrote months or years ago, show both and name the thread. Reminding them that they have been here before, and what they learned then, is the most valuable thing you can do.
3. Use the RECENT NOTES to understand what is on their mind now, and the OLDER NOTES to remind them what they already know about it.
4. Be calm and clear. Short, direct and grounded: no hype, no long lists. If one insight matters most, lead with it, and stop when you have said it.
5. Do not push them to read, research or learn more, or suggest notes they should write. If their notes do not cover something, say so in one line. Bring in general knowledge only when they ask for it, and label it as yours rather than theirs.
6. If they open with just "hey" or "hello", reflect back, briefly, one or two things that seem to be on their mind from their recent notes, and one thing they already know that could help with it.

When referencing notes, always use the exact format [[filename.md]]: double brackets, the .md extension, no spaces inside the brackets. For example: "You wrote about this in [[Temple.md]] and again in [[2025-10-27.md]]." Never use single brackets or parentheses."""
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings() 