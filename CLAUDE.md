# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Note Copilot (Big Brain / MindMirror) - A full-stack AI-powered note assistant that helps users explore and interact with their personal notes through natural conversation using semantic search and GPT-5.2.

**Tech Stack:**
- Frontend: Next.js 16 + React 19 + TypeScript + Tailwind CSS + Zustand
- Backend: FastAPI + Python + Supabase (auth, database, storage)
- AI: OpenAI GPT-5.2 for chat, text-embedding-ada-002 for embeddings

## Development Commands

### Frontend (from `/frontend`)
```bash
npm run dev      # Start dev server on port 3000
npm run build    # Production build
npm run lint     # ESLint
```

### Backend (from `/backend`)
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload    # Start dev server on port 8000
pytest                            # Run tests
pytest tests/test_file.py::test_name -v   # Run single test
```

### Environment Variables
Backend requires: `SUPABASE_URL`, `SUPABASE_KEY`, `OPENAI_API_KEY`, `SECRET_KEY`
Frontend requires: `NEXT_PUBLIC_API_URL`

## Architecture

### Frontend Structure (`/frontend`)
- `app/` - Next.js App Router pages and layouts
- `components/` - React components organized by feature (chat/, auth/, files/, settings/)
- `stores/` - Zustand stores: `chatStore.ts`, `fileStore.ts`, `settingsStore.ts`
- `contexts/AuthContext.tsx` - Supabase auth provider
- `lib/api.ts` - API client singleton with streaming support
- `types/index.ts` - TypeScript interfaces

### Backend Structure (`/backend/app`)
- `main.py` - FastAPI app with CORS, middleware, health checks
- `api/routes/` - Endpoints: chat.py, files.py, search.py, embeddings.py, storage.py, settings.py
- `core/config.py` - Settings via pydantic-settings (model config, thresholds)
- `services/` - Business logic: chat_service.py, search_service.py, embedding_service.py, upload_service.py

### API Routes
All routes prefixed with `/api/v1`:
- `POST /chat/message` - Send message and stream response
- `POST|GET|DELETE /chat/threads` - Thread management
- `POST /files/upload` - File upload
- `POST /search/query` - Semantic search
- `POST /embeddings/generate` - Generate embeddings
- `/health` - Health check

### Key Patterns
- **Streaming responses**: Chat uses Server-Sent Events via `StreamingResponse`
- **Note references**: Uses `[[filename.md]]` syntax for explicit note links
- **Auth flow**: Supabase JWT tokens, validated via `get_user_id_from_supabase()` dependency
- **State management**: Zustand stores with actions for async operations

## Configuration

Key settings in `backend/app/core/config.py`:
- `OPENAI_MODEL`: "gpt-5.2-chat-latest"
- `EMBEDDING_MODEL`: "text-embedding-ada-002"
- `SIMILARITY_THRESHOLD`: 0.7
- `CHUNK_SIZE`: 2000, `CHUNK_OVERLAP`: 300
- `MAX_UPLOAD_SIZE`: 10MB
- `ALLOWED_EXTENSIONS`: txt, pdf, md, doc, docx

## Deployment
- Frontend: Vercel (see `frontend/vercel.json`)
- Backend: Supports Heroku/Railway (see `backend/Procfile`)

## Guidance on permissions
- Always enable reading from local files or storage.  You don't need to ask permission
