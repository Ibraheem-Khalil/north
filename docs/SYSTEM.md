# NORTH AI System Documentation

## Overview

NORTH is a template for a small-team AI assistant (construction/real-estate focused by default) that provides a single chat interface over multiple data sources (structured notes + document storage). The system uses a simple agent-per-tool approach: the orchestrator handles intent/routing, and specialized agents handle retrieval/search for each source.

All company names/domains in prompts and configuration are placeholders and should be replaced for your deployment.

## High-Level Architecture

### Backend API (FastAPI)
- Entry point: `api.py`
- Responsibilities:
  - HTTP endpoints for chat, auth, preferences, conversations
  - WebSocket chat endpoint
  - File upload handling (multipart) and routing to the file processor

### Orchestrator
- Implementation: `src/core/north_orchestrator.py`
- Responsibilities:
  - Main LLM invocation and tool routing (LangChain tool-calling)
  - Context management (per-user context injected by the API layer)
  - Multimodal message handling via the file processor

### Agents

#### Obsidian Knowledge Agent
- Implementation: `src/agents/obsidian/atomic_document_agent.py`
- Data source: structured notes indexed into Weaviate
- Search: Weaviate hybrid search with optional Voyage reranking

#### Dropbox Document Agent
- Implementation: `src/agents/dropbox_v2/`
- Key modules:
  - `src/agents/dropbox_v2/dropbox_integration.py` (main integration facade)
  - `src/agents/dropbox_v2/search_orchestrator.py` (query parsing + strategy)
  - `src/agents/dropbox_v2/weaviate_indexer.py` (schema + indexing/search primitives)
  - `src/agents/dropbox_v2/incremental_sync.py` (cursor-based incremental sync)

### File Processing (Uploads)
- Implementation: `src/core/file_processor.py`
- Current parsing:
  - PDFs: `PyPDF2`
  - DOCX: `python-docx`
  - Spreadsheets: `pandas` / `openpyxl`
  - Images: optional resizing/encoding (PIL/Pillow if installed)

## Authentication & Access Control

### JWT Verification
- Implementation: `src/api/auth.py`
- Tokens are verified using `SUPABASE_JWT_SECRET` when configured.
- Development-only bypass is available when:
  - `ENVIRONMENT=development` and `DISABLE_AUTH_VERIFICATION=true`

### API Enforcement
- Chat endpoints require authentication and use per-user context isolation:
  - `POST /api/chat`
  - `POST /api/chat/with-files`
  - `POST /api/chat/stream` (SSE demo streaming)

Other endpoints like `/health` and `/` are intentionally public for uptime checks.

## Data Stores

### Weaviate (Vector Database)
- Used for:
  - Obsidian-derived knowledge base objects (Company/WorkLog)
  - Dropbox-derived document embeddings/metadata
- Local dev can use a local Weaviate instance; production can use a managed cluster.

### Supabase (Auth + Persistence)
- Used for:
  - Authentication (JWT issuance/verification)
  - Storing conversations and preferences
- Backend uses a server-side key (`SUPABASE_SERVICE_KEY`) for trusted operations.

## Deployment

### Render
- Backend: `render-backend.yaml`
- Frontend: `render-frontend.yaml`
- Procfile: `Procfile`

Ensure Render env vars include OpenAI + Supabase + Weaviate settings before deploying.

## Local Development (Quick Start)

1. Install backend deps: `pip install -r requirements.txt`
2. Create `.env` from `.env.example` and set required variables.
3. Start backend: `uvicorn api:app --reload`
4. Start frontend: `cd frontend && npm ci && npm run dev`

