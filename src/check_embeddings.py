import asyncio
from src.storage_service import get_all_embeddings

async def check_embeddings():
    """Check stored embeddings."""
    embeddings = await get_all_embeddings()
    print(f"Found {len(embeddings)} embeddings:")
    for emb in embeddings:
        print(f"- {emb['id']}: {len(emb['embedding'])} dimensions")

if __name__ == "__main__":
    asyncio.run(check_embeddings()) 