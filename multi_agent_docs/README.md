# Multi-Agent Code Analysis & Documentation System
## HUE 25.12 — Python (FastAPI) + GenAI Track

An AI-powered system that transforms any codebase into comprehensive, role-specific documentation using a pipeline of 7 specialized LangGraph agents.

---

## Milestones Implemented

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Foundation — Auth, project creation, file upload, invalid file handling | |
| 2 | Intelligent Preprocessing — Repo detection, code chunking, ChromaDB search | |
| 3 | Real-Time Progress — Polling-based live feed, activity log, SSE endpoint | |
| 4 | Multi-Agent Orchestra — 7 LangGraph agents, web search, persona routing | |
| 5 | Interactive Control — Pause/resume, Q&A during analysis, context injection | |
| 6 | Rich Outputs — SDE + PM docs, Q&A, 5 Mermaid diagrams, PDF/MD export | |
| 7 | Observability & Admin — Admin CRUD, token tracking, agent traces | |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Git (for GitHub URL import)

### 1. Clone & Setup
```bash
# Copy environment config
cp .env.example .env

# Edit .env and add your OPENAI_API_KEY (required)
nano .env
```

### 2. Run Everything
```bash
chmod +x run.sh
./run.sh
```

Or manually:
```bash
# Terminal 1 - Backend
pip install -r backend/requirements.txt
PYTHONPATH=. uvicorn backend.main:app --reload --port 8000

# Terminal 2 - Frontend  
pip install -r frontend/requirements.txt
PYTHONPATH=. streamlit run frontend/app.py
```

### 3. Open in Browser
- **Frontend**: http://localhost:8501
- **API Docs (Swagger)**: http://localhost:8000/docs

---

## Architecture

```
multi_agent_docs/
├── backend/
│   ├── main.py              # FastAPI app, all routes, SSE
│   ├── auth.py              # JWT authentication  
│   ├── database.py          # SQLite models (SQLAlchemy)
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── crud.py              # Database operations
│   ├── config.py            # Configuration management
│   ├── agents/
│   │   ├── state.py         # LangGraph TypedDict state
│   │   ├── orchestrator.py  # LangGraph graph definition
│   │   └── agent_nodes.py   # 7 agent implementations
│   └── utils/
│       ├── code_chunker.py  # Code chunking (Python, JS, etc.)
│       ├── vector_store.py  # ChromaDB semantic search
│       ├── file_processor.py # ZIP/GitHub processing
│       └── pdf_exporter.py  # fpdf2 PDF generation
└── frontend/
    ├── app.py               # Main Streamlit app + auth
    ├── components/
    │   └── mermaid.py       # Fixed Mermaid renderer (CDN JS)
    ├── utils/
    │   └── api_client.py    # HTTP client for backend
    └── pages/
        ├── 1_Dashboard.py   # Project dashboard
        ├── 2_New_Project.py # Project creation
        ├── 3_Analysis.py    # Real-time monitoring + Q&A
        ├── 4_Documentation.py # SDE/PM docs + diagrams + export
        └── 5_Admin.py       # Admin panel
```

---

## The 7 Agents

| # | Agent | Responsibility |
|---|-------|----------------|
| 1 | **FileStructureAgent** | Walks file tree, detects repo type, entry points |
| 2 | **CodeChunkingAgent** | Chunks code, indexes in ChromaDB for semantic search |
| 3 | **APIExtractorAgent** | Extracts endpoints, DB models, auth patterns via LLM |
| 4 | **WebSearchAgent** | Searches DuckDuckGo for latest best practices |
| 5 | **SDEDocAgent** | Generates comprehensive SDE documentation |
| 6 | **PMDocAgent** | Generates business-focused PM documentation |
| 7 | **DiagramAgent** | Generates 5 Mermaid diagrams (arch, sequence, ER, flow, auth) |

---

## ️ Tech Stack

| Component | Technology | Notes |
|-----------|------------|-------|
| Agent Orchestration | **LangGraph** | DAG with checkpointing |
| Backend API | **FastAPI** | + Swagger docs |
| Frontend | **Streamlit** | Multi-page app |
| Vector Search | **ChromaDB** | In-process, no install needed |
| Database | **SQLite** | Via SQLAlchemy, no install needed |
| LLM | **OpenAI / Anthropic** | Configurable |
| Web Search | **DuckDuckGo** | No API key required |
| PDF Export | **fpdf2** | Pure Python |
| Real-time | **SSE + Polling** | Server-Sent Events |
| Observability | **Langfuse** (optional) | Token/cost tracking |

> **Note:** SQLite replaces PostgreSQL+pgvector as they require external service installation. ChromaDB provides equivalent semantic search capabilities with zero external dependencies.

---

## Configuration

All config in `.env`:

```env
# Required
OPENAI_API_KEY=sk-...

# Optional LLM override
LLM_PROVIDER=openai          # or anthropic
LLM_MODEL=gpt-4o-mini        # or gpt-4o, claude-3-haiku, etc.

# Optional: Langfuse observability  
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

---

## API Reference

Full Swagger documentation available at **http://localhost:8000/docs**

Key endpoints:
- `POST /api/auth/signup` — Register user (User or Admin role)
- `POST /api/auth/login-json` — Authenticate
- `POST /api/projects/upload` — Create project (ZIP or GitHub URL)
- `POST /api/projects/{id}/start` — Start analysis pipeline
- `POST /api/projects/{id}/pause` — Pause analysis
- `POST /api/projects/{id}/resume` — Resume with optional context
- `GET /api/projects/{id}/stream?token=...` — SSE progress stream
- `GET /api/projects/{id}/documents/{persona}` — Get SDE or PM doc
- `GET /api/projects/{id}/diagrams` — Get all Mermaid diagrams
- `POST /api/projects/{id}/qa` — Ask question about codebase
- `GET /api/projects/{id}/export/pdf` — Download PDF
- `GET /api/projects/{id}/search?q=...` — Semantic code search
- `GET /api/admin/users` — List all users (admin)
- `GET /api/admin/stats` — System statistics (admin)

---

##  Bug Fixes Applied

1. **Mermaid diagrams not rendering** → Fixed by using official Mermaid 10.x CDN JS via `st.components.v1.html()` instead of unreliable libraries. Added fallback diagram generation when LLM produces invalid syntax.

2. **PM documentation missing as separate tab** → PM documentation now has its own dedicated tab in the Documentation page, completely separate from SDE. Both are stored and retrieved independently from the database.

---

##  User Flow (per requirements)

1. **Authentication** — Signup/login with User or Admin role
2. **Project Creation** — Upload ZIP or GitHub URL, select SDE/PM personas, configure agents
3. **Active Analysis** — Monitor real-time progress, pause/resume, inject context, ask Q&A
4. **Documentation Review** — View structured SDE & PM reports, explore diagrams, Q&A
5. **Export** — Download Markdown or PDF

---

## License
HUE 25.12 Academic Project
