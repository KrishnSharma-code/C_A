# HUE 25.12 — Multi-Agent Code Analysis & Documentation System
## Project Overview, Milestone Status, Tech Stack & Code Explanation

---

## Milestone Status

| # | Milestone | Status | Notes |
|---|-----------|--------|-------|
| 1 | Repository Ingestion — ZIP upload + GitHub/Gist clone |  Complete | Validates ZIP, extracts, or clones with `gitpython`. Gist URLs supported. |
| 2 | Multi-Agent LangGraph Orchestration (5+ agents) |  Complete | 7 agents in a directed graph: File→Chunk→API→Web→SDE→PM→Diagram |
| 3 | SDE Documentation Generation |  Complete | Full technical doc: architecture, APIs, DB schema, setup, auth, error handling, performance |
| 4 | PM Documentation Generation (separate tab) |  Complete | Business-focused: product overview, feature inventory (codebase-grounded), user journeys, roadmap |
| 5 | 5 Mermaid Diagram Types |  Complete | Architecture (graph TD), Sequence, ER, User Flow (flowchart TD), Auth Flow (flowchart LR) |
| 6 | Interactive Q&A |  Complete | Answers grounded in generated docs + ChromaDB code search; progress bar + countdown |
| 7 | Export — Markdown + PDF |  Complete | Full Markdown export; PDF via fpdf2. Both have progress bars + countdown. |
| + | Real-time SSE progress tracking |  Complete | SSE stream + 3s polling fallback; per-agent progress with milestone badges |
| + | Pause / Resume with user context injection |  Complete | asyncio.Event per project; context fed into subsequent agents |
| + | JWT Authentication + signup/login |  Complete | bcrypt hashing, JWT tokens, role-based (user/admin) |
| + | Admin Dashboard |  Complete | User CRUD, project management, system health stats |
| + | Langfuse Observability hooks |  Complete | Optional; activate by setting LANGFUSE_* keys in .env |
| + | Semantic Code Search |  Complete | ChromaDB vector store, natural language query over code chunks |

> All 7 required milestones and all supporting features are implemented.

---

## Known Limitations

- **Feature Inventory accuracy** depends on what the LLM can infer from extracted API endpoints and key features. Very small or test repos may produce generic PM docs.
- **Q&A quality** requires a valid `OPENAI_API_KEY` in `.env`. Without it, only the fallback message is shown.
- **Diagrams** require internet access to `mermaid.ink` for rendering.
- **PDF formatting** is functional but plain (no custom fonts/images) — uses `fpdf2` pure-Python approach to avoid external installs.

---

## Tech Stack

### Backend
| Component | Technology | Why |
|-----------|-----------|-----|
| API Framework | **FastAPI** | Async-native, auto Swagger docs, modern Python |
| Authentication | **python-jose** (JWT) + **bcrypt** | Stateless JWT, no external auth service needed |
| Database | **SQLite** + **SQLAlchemy** (ORM) | Zero external install; sufficient for single-node |
| Vector Store | **ChromaDB** (in-process) | No separate vector DB process; stores code embeddings locally |
| Agent Framework | **LangGraph** | DAG-based multi-agent orchestration with state passing |
| LLM Integration | **LangChain** + **langchain-openai** | Abstracts LLM provider; supports OpenAI and Anthropic |
| Web Search | **DuckDuckGo Search** (`duckduckgo-search`) | No API key required |
| Code Ingestion | **gitpython** | Clones GitHub/Gist repos programmatically |
| PDF Export | **fpdf2** | Pure Python, no OS-level dependencies |
| Real-time | **SSE** (Server-Sent Events via FastAPI `StreamingResponse`) | Push progress updates without WebSockets |
| Observability | **Langfuse** (optional) | LLM trace logging when keys provided |

### Frontend
| Component | Technology | Why |
|-----------|-----------|-----|
| UI Framework | **Streamlit** | Rapid Python-native UI; multi-page app |
| Diagram Rendering | **mermaid.ink** API | Server-side SVG/PNG rendering; no CDN JS in iframe |
| API Client | **requests** | HTTP calls to FastAPI backend |
| Progress UX | **threading** + `st.progress` | Background HTTP request + live countdown in main thread |

### Infrastructure
| Component | Technology |
|-----------|-----------|
| Concurrency | Python `asyncio` + `asyncio.to_thread` for blocking calls |
| File Storage | Local filesystem (`uploads/`, `chroma_db/`, `data/`) |
| Config | `.env` + `python-dotenv` |

---

## Code Explanation

### Directory Structure
```
multi_agent_docs/
├── backend/
│   ├── main.py              # FastAPI app, all routes, SSE endpoint, background task runner
│   ├── database.py          # SQLAlchemy models: User, Project, Document, Diagram, AgentTrace, QAEntry
│   ├── auth.py              # JWT creation/validation, bcrypt password hashing
│   ├── crud.py              # Database CRUD operations (thin layer over SQLAlchemy)
│   ├── config.py            # Environment variable loading and path constants
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── agents/
│   │   ├── orchestrator.py  # LangGraph StateGraph definition and compilation
│   │   ├── agent_nodes.py   # All 7 agent implementations + Q&A agent
│   │   └── state.py         # TypedDict for the shared analysis state
│   └── utils/
│       ├── code_chunker.py  # Language-aware code splitting (Python, JS, generic)
│       ├── vector_store.py  # ChromaDB wrapper (add, search, delete)
│       ├── file_processor.py# ZIP validation/extraction, GitHub/Gist clone, URL validation
│       └── pdf_exporter.py  # fpdf2 PDF generation from markdown content
├── frontend/
│   ├── app.py               # Main Streamlit entry: login/signup page, session management
│   ├── pages/
│   │   ├── 1_Dashboard.py   # Project list, status cards, quick-start
│   │   ├── 2_New_Project.py # ZIP upload / GitHub URL, persona/config selection
│   │   ├── 3_Analysis.py    # Live monitoring: progress bar, pause/resume, Q&A during analysis
│   │   ├── 4_Documentation.py# SDE tab, PM tab, Diagrams, Q&A, Export (all with progress bars)
│   │   └── 5_Admin.py       # Admin: user management, project list, system stats
│   ├── components/
│   │   └── mermaid.py       # Mermaid renderer via mermaid.ink API (bytes → st.image)
│   └── utils/
│       └── api_client.py    # Typed HTTP wrapper for all backend endpoints
├── .env.example             # Template — copy to .env and add OPENAI_API_KEY
├── run.bat                  # Windows one-click startup
└── run.sh                   # Linux/Mac one-click startup
```

### Agent Pipeline (LangGraph)

```
START
  │
  ▼
[1] FileStructureAgent
    - Walks file tree, detects repo type (FastAPI, Express, Django, etc.)
    - Identifies entry points, config files
  │
  ▼
[2] CodeChunkingAgent
    - Splits code into chunks by function/class (language-aware)
    - Indexes chunks in ChromaDB with embeddings
  │
  ▼
[3] APIExtractorAgent  ← first LLM call
    - Extracts endpoints, DB models, auth patterns, tech stack
    - Uses LLM over sampled code chunks
  │
  ▼
[4] WebSearchAgent
    - DuckDuckGo searches for best practices, common patterns for detected tech
    - Results fed as context to doc agents
  │
  ▼
[5] SDEDocAgent  ← LLM call
    - Generates full SDE markdown document using all extracted state
  │
  ▼
[6] PMDocAgent  ← LLM call
    - Generates PM markdown doc — grounded strictly in detected features
  │
  ▼
[7] DiagramAgent  ← 5 LLM calls (one per diagram)
    - Architecture, Sequence, ER, User Flow, Auth Flow
    - Validates and auto-fixes Mermaid syntax
  │
  ▼
END
```

### Key Design Decisions

**1. SQLite instead of PostgreSQL**
Avoids requiring a database server install. For this project scope (single-node, small teams) SQLite is sufficient. The SQLAlchemy ORM makes migration to Postgres trivial by changing one connection string.

**2. ChromaDB in-process instead of pgvector**
pgvector requires a Postgres extension and specific setup. ChromaDB runs fully in-process, persists to disk, and needs zero configuration. Performance is adequate for codebases up to ~10,000 files.

**3. asyncio.to_thread for blocking operations**
`clone_github_repo`, `extract_zip`, and other file operations are synchronous. Wrapping them in `asyncio.to_thread()` keeps FastAPI's event loop free so other requests (like `GET /api/projects/{id}`) can still be served during analysis.

**4. SSE for real-time updates**
Server-Sent Events are simpler than WebSockets for one-directional push. The frontend polls every 3 seconds as a fallback for browsers that drop SSE connections.

**5. uvicorn --reload-dir backend**
Limits the file watcher to the `backend/` directory only. Without this, uvicorn's reloader detects ChromaDB writing to `chroma_db/` and restarts the server mid-analysis, cancelling the analysis task.

**6. mermaid.ink for diagram rendering**
Streamlit's `st.components.v1.html()` runs in a sandboxed iframe that blocks external CDN scripts. `mermaid.ink` renders Mermaid code server-side and returns a PNG, which is fetched as bytes and displayed via `st.image(bytes)` — works on all Streamlit versions.

**7. Q&A grounded in generated docs**
The Q&A agent first loads the generated SDE/PM document (4000 chars) as primary context, then adds 3 relevant ChromaDB code chunks. This produces more coherent answers and uses fewer tokens than querying raw code alone, because the doc is already an LLM-summarised view of the codebase.

---

## Doc Gaps vs Requirements (from attached abc_documentation.md)

| Section | Status | Notes |
|---------|--------|-------|
| Technical Architecture Overview |  Present | Includes component relationships, design patterns |
| API Documentation (table) |  Present | Full endpoint table with method/path/input/output |
| Database Schema & Data Models |  Present | Model list with fields |
| Code Structure & Module Dependencies |  Present | Folder tree + dependency list |
| Setup & Deployment Guide |  Present | Prerequisites, install steps, Docker example |
| Authentication & Security |  Present | Patterns, best practices |
| Error Handling |  Present | Strategies listed |
| Performance Considerations |  Present | Caching, optimization, bottlenecks |
| Development Guidelines |  Present | Coding standards, testing, contribution |
| PM: Product Overview + Mission |  Present | |
| PM: Target Users |  Present | |
| PM: Feature Inventory (Core/Supporting/Admin) | ️ Improved | Prompt now enforces codebase-grounded inventory only |
| PM: User Journey Flows |  Present | |
| PM: Business Rules & Logic |  Present | |
| PM: Integration Points |  Present | |
| PM: Data & Analytics |  Present | |
| PM: Technical Constraints |  Present | |
| PM: Roadmap Implications |  Present | |
| Mermaid Diagrams (5 types) |  Present | Rendered via mermaid.ink |

**Key observation:** The Feature Inventory was generating generic features (notifications, mobile app, etc.) for repos that don't have those. This has been fixed with an explicit `️ CRITICAL RULE` in the PM agent prompt to base features strictly on detected endpoints and code analysis.
