"""
FastAPI Backend - Multi-Agent Code Analysis & Documentation System
All API routes, SSE streaming, and WebSocket support.
"""
import asyncio
import json
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import (
    FastAPI, Depends, HTTPException, UploadFile, File, Form,
    BackgroundTasks, Request, status
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.config import UPLOADS_DIR, BACKEND_URL, FRONTEND_URL
from backend.database import get_db, User, Project
from backend.auth import (
    authenticate_user, create_access_token, get_current_user,
    get_current_admin, get_password_hash
)
from backend.schemas import (
    UserCreate, UserLogin, UserOut, TokenResponse,
    ProjectCreate, ProjectUpdate, ProjectOut,
    LogOut, DocumentOut, DiagramOut,
    QARequest, QAResponse, QAEntryOut,
    ResumeRequest, UserContextRequest,
    AdminStats, UserAdminUpdate, AgentTraceOut
)
from backend import crud

# App setup
app = FastAPI(
    title="Multi-Agent Code Analysis System",
    description="HUE 25.12 - AI-powered codebase documentation with multi-agent LangGraph orchestration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory analysis state
# project_id -> asyncio.Queue of progress events
_sse_queues: Dict[str, asyncio.Queue] = {}
# project_id -> asyncio.Task
_analysis_tasks: Dict[str, asyncio.Task] = {}
# project_id -> current summary state (for Q&A)
_project_summaries: Dict[str, dict] = {}


# AUTH ROUTES
@app.post("/api/auth/signup", response_model=TokenResponse, tags=["Authentication"])
async def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user (User or Admin role)."""
    # Check email exists
    if crud.get_user_by_email(db, user_data.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check username exists
    existing = db.query(User).filter(User.username == user_data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    user = crud.create_user(
        db,
        email=user_data.email,
        username=user_data.username,
        password=user_data.password,
        role=user_data.role
    )

    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(user)
    )


@app.post("/api/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login with email and password."""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(user)
    )


@app.post("/api/auth/login-json", response_model=TokenResponse, tags=["Authentication"])
async def login_json(credentials: UserLogin, db: Session = Depends(get_db)):
    """Login with JSON body (for frontend use)."""
    user = authenticate_user(db, credentials.email, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(user)
    )


@app.get("/api/auth/me", response_model=UserOut, tags=["Authentication"])
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info."""
    return current_user


# PROJECT ROUTES
@app.get("/api/projects", response_model=List[ProjectOut], tags=["Projects"])
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List user's projects."""
    projects = crud.get_user_projects(db, current_user.id)
    return projects


@app.post("/api/projects", response_model=ProjectOut, tags=["Projects"])
async def create_project(
    project_data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new project (without file upload)."""
    project = crud.create_project(
        db,
        user_id=current_user.id,
        name=project_data.name,
        description=project_data.description,
        personas=project_data.personas,
        analysis_config=project_data.analysis_config.model_dump()
    )
    return project


@app.post("/api/projects/upload", response_model=ProjectOut, tags=["Projects"])
async def create_project_with_upload(
    name: str = Form(...),
    description: str = Form(""),
    personas: str = Form('["sde","pm"]'),
    analysis_config: str = Form('{}'),
    zip_file: Optional[UploadFile] = File(None),
    github_url: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a project with ZIP upload or GitHub URL."""
    import json as json_lib
    from backend.utils.file_processor import (
        validate_zip, extract_zip, validate_github_url, clone_github_repo
    )

    # Parse JSON fields
    try:
        personas_list = json_lib.loads(personas)
    except Exception:
        personas_list = ["sde", "pm"]

    try:
        config_dict = json_lib.loads(analysis_config) if analysis_config else {}
    except Exception:
        config_dict = {}

    # Validate that either zip or github_url is provided
    if not zip_file and not github_url.strip():
        raise HTTPException(status_code=400, detail="Either a ZIP file or GitHub URL is required")

    # Create project record
    project = crud.create_project(
        db,
        user_id=current_user.id,
        name=name,
        description=description,
        personas=personas_list,
        analysis_config=config_dict
    )

    project_upload_dir = UPLOADS_DIR / project.id
    project_upload_dir.mkdir(parents=True, exist_ok=True)

    try:
        if zip_file:
            # Handle ZIP upload
            from backend.config import MAX_FILE_SIZE_BYTES

            # Check file extension
            filename = zip_file.filename or "upload.zip"
            ext = Path(filename).suffix.lower()
            if ext not in {".zip"}:
                crud.delete_project(db, project.id)
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file format: {ext}. Only .zip files are accepted (not .rar, .7z, etc.)"
                )

            # Save uploaded file
            zip_path = project_upload_dir / filename
            content = await zip_file.read()
            if len(content) > MAX_FILE_SIZE_BYTES:
                crud.delete_project(db, project.id)
                raise HTTPException(
                    status_code=400,
                    detail=f"File too large ({len(content) // (1024*1024)}MB). Maximum allowed: 100MB"
                )

            with open(zip_path, "wb") as f:
                f.write(content)

            # Validate zip (run in thread to avoid blocking event loop)
            valid, msg = await asyncio.to_thread(validate_zip, str(zip_path))
            if not valid:
                crud.delete_project(db, project.id)
                shutil.rmtree(project_upload_dir, ignore_errors=True)
                raise HTTPException(status_code=400, detail=msg)

            # Extract zip (run in thread to avoid blocking event loop)
            success, msg, extract_path = await asyncio.to_thread(extract_zip, str(zip_path), project.id)
            if not success:
                crud.delete_project(db, project.id)
                shutil.rmtree(project_upload_dir, ignore_errors=True)
                raise HTTPException(status_code=400, detail=msg)

            crud.update_project(
                db, project.id,
                repo_source="zip",
                zip_filename=filename,
                upload_path=str(zip_path),
                extracted_path=extract_path,
                status="ready"
            )

        elif github_url.strip():
            # Handle GitHub URL
            valid, msg = validate_github_url(github_url)
            if not valid:
                crud.delete_project(db, project.id)
                raise HTTPException(status_code=400, detail=msg)

            # Clone in background during analysis start
            crud.update_project(
                db, project.id,
                github_url=github_url,
                repo_source="github",
                status="ready"
            )

    except HTTPException:
        raise
    except Exception as e:
        crud.delete_project(db, project.id)
        shutil.rmtree(project_upload_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Project creation failed: {str(e)}")

    db.refresh(project)
    crud.add_log(db, project.id, f"Project '{name}' created. Ready for analysis.", "milestone")
    return project


@app.get("/api/projects/{project_id}", response_model=ProjectOut, tags=["Projects"])
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    return project


@app.delete("/api/projects/{project_id}", tags=["Projects"])
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    # Cancel running analysis
    if project_id in _analysis_tasks:
        _analysis_tasks[project_id].cancel()
        del _analysis_tasks[project_id]

    # Cleanup files
    upload_dir = UPLOADS_DIR / project_id
    shutil.rmtree(upload_dir, ignore_errors=True)

    # Cleanup vector store
    try:
        from backend.utils.vector_store import CodeVectorStore
        CodeVectorStore(project_id).delete_collection()
    except Exception:
        pass

    crud.delete_project(db, project_id)
    return {"message": "Project deleted"}


# ANALYSIS CONTROL
@app.post("/api/projects/{project_id}/start", tags=["Analysis"])
async def start_analysis(
    project_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start the multi-agent analysis pipeline."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    if project.status in ("analyzing", "preprocessing"):
        raise HTTPException(status_code=400, detail="Analysis already running")
    if project.status == "created":
        raise HTTPException(status_code=400, detail="Please upload a repository first")

    # Initialize SSE queue
    _sse_queues[project_id] = asyncio.Queue(maxsize=500)

    # Update status
    crud.update_project(db, project_id, status="preprocessing", progress=0, error_message="")
    crud.add_log(db, project_id, "Analysis started", "milestone")

    # Start background analysis
    loop = asyncio.get_event_loop()
    task = loop.create_task(_run_analysis(project_id, project))
    _analysis_tasks[project_id] = task

    return {"message": "Analysis started", "project_id": project_id}


async def _run_analysis(project_id: str, project):
    """Background task: run the full LangGraph analysis pipeline."""
    from backend.agents.agent_nodes import (
        register_project, cleanup_project, set_progress_callback
    )
    from backend.agents.orchestrator import get_graph

    # Create a new DB session for background task
    from backend.database import SessionLocal
    db = SessionLocal()

    try:
        # Register project for pause/resume control
        register_project(project_id)

        async def progress_callback(pid: str, message: str, progress: int,
                                    level: str = "info", agent: str = "system"):
            """Callback for progress updates from agents."""
            try:
                crud.add_log(db, pid, message, level, agent)
                crud.update_project(db, pid, progress=progress, current_agent=agent)

                event_data = {
                    "type": "progress",
                    "message": message,
                    "progress": progress,
                    "level": level,
                    "agent": agent,
                    "timestamp": datetime.utcnow().isoformat()
                }
                if pid in _sse_queues:
                    try:
                        _sse_queues[pid].put_nowait(event_data)
                    except asyncio.QueueFull:
                        pass
            except Exception:
                pass

        set_progress_callback(project_id, progress_callback)

        # Resolve repo path
        repo_path = project.extracted_path
        if not repo_path:
            # GitHub URL - clone now
            if project.github_url:
                await progress_callback(project_id, "Cloning GitHub repository...", 2, "info", "system")
                from backend.utils.file_processor import clone_github_repo, validate_github_url
                success, msg, cloned_path = await asyncio.to_thread(
                    clone_github_repo, project.github_url, project_id
                )
                if not success:
                    raise ValueError(f"GitHub clone failed: {msg}")
                repo_path = cloned_path
                crud.update_project(db, project_id, extracted_path=repo_path)
                await progress_callback(project_id, f"Repository cloned successfully", 3, "milestone", "system")
            else:
                raise ValueError("No repository path available")

        if not Path(repo_path).exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")

        # Build initial state
        analysis_config = project.analysis_config or {}
        initial_state: dict = {
            "project_id": project_id,
            "repo_path": repo_path,
            "personas": project.personas or ["sde", "pm"],
            "analysis_depth": analysis_config.get("depth", "standard"),
            "verbosity": analysis_config.get("verbosity", "medium"),
            "generate_diagrams": analysis_config.get("generate_diagrams", True),
            "web_search_enabled": analysis_config.get("web_search", True),
            "focus_areas": analysis_config.get("focus_areas", []),
            # Initialize all state fields
            "repo_type": "",
            "entry_points": [],
            "config_files": [],
            "dependencies": {},
            "file_tree": {},
            "important_files": [],
            "total_files": 0,
            "all_chunks": [],
            "total_chunks": 0,
            "api_endpoints": [],
            "db_models": [],
            "auth_patterns": [],
            "business_logic": [],
            "key_features": [],
            "tech_stack": [],
            "web_findings": {},
            "sde_report": "",
            "pm_report": "",
            "diagrams": {},
            "is_paused": False,
            "pause_requested": False,
            "current_agent": "system",
            "progress": 0,
            "messages": [],
            "user_context": [],
            "errors": [],
            "trace_data": []
        }

        crud.update_project(db, project_id, status="analyzing")
        await progress_callback(project_id, "Starting multi-agent analysis pipeline...", 1, "milestone", "system")

        # Run the LangGraph pipeline
        graph = get_graph()
        config = {"configurable": {"thread_id": project_id}}

        final_state = None
        async for event in graph.astream(initial_state, config=config):
            for node_name, node_output in event.items():
                if isinstance(node_output, dict):
                    final_state = node_output
                # Emit SSE event for node completion
                event_data = {
                    "type": "agent_complete",
                    "agent": node_name,
                    "timestamp": datetime.utcnow().isoformat()
                }
                if project_id in _sse_queues:
                    try:
                        _sse_queues[project_id].put_nowait(event_data)
                    except asyncio.QueueFull:
                        pass

        # Get final state from checkpoint
        final = graph.get_state(config)
        if final and final.values:
            final_state = final.values

        # Save results to database
        await progress_callback(project_id, "Saving documentation to database...", 96, "info", "system")

        if final_state:
            # Save SDE document
            sde_report = final_state.get("sde_report", "")
            if sde_report and "sde" in project.personas:
                crud.upsert_document(db, project_id, "sde", "SDE Documentation", sde_report)

            # Save PM document
            pm_report = final_state.get("pm_report", "")
            if pm_report and "pm" in project.personas:
                crud.upsert_document(db, project_id, "pm", "PM Documentation", pm_report)

            # Save diagrams
            diagrams = final_state.get("diagrams", {})
            for diagram_type, diagram_data in diagrams.items():
                if isinstance(diagram_data, dict) and diagram_data.get("mermaid_code"):
                    crud.save_diagram(
                        db, project_id,
                        diagram_type=diagram_type,
                        title=diagram_data.get("title", diagram_type),
                        description=diagram_data.get("description", ""),
                        mermaid_code=diagram_data.get("mermaid_code", ""),
                        persona=diagram_data.get("persona", "both")
                    )

            # Save agent traces
            trace_data = final_state.get("trace_data", [])
            for trace in trace_data:
                if trace and isinstance(trace, dict):
                    input_tok = trace.get("input_tokens", 0)
                    output_tok = trace.get("output_tokens", 0)
                    # Estimate cost (gpt-4o-mini pricing)
                    cost = (input_tok * 0.00015 + output_tok * 0.0006) / 1000
                    crud.save_trace(
                        db, project_id,
                        agent_name=trace.get("agent_name", "unknown"),
                        input_tokens=input_tok,
                        output_tokens=output_tok,
                        cost_usd=cost,
                        latency_ms=trace.get("latency_ms", 0)
                    )

            # Store summary for Q&A
            _project_summaries[project_id] = {
                "repo_type": final_state.get("repo_type", ""),
                "api_endpoints": final_state.get("api_endpoints", []),
                "tech_stack": final_state.get("tech_stack", []),
                "key_features": final_state.get("key_features", []),
                "db_models": final_state.get("db_models", []),
                "auth_patterns": final_state.get("auth_patterns", [])
            }

            # Update project metadata
            crud.update_project(
                db, project_id,
                repo_type=final_state.get("repo_type", ""),
                status="completed",
                progress=100,
                current_agent=""
            )

        await progress_callback(project_id, "Analysis complete! Documentation ready.", 100, "milestone", "system")

        # Signal SSE completion
        if project_id in _sse_queues:
            _sse_queues[project_id].put_nowait({
                "type": "complete",
                "message": "Analysis complete",
                "timestamp": datetime.utcnow().isoformat()
            })

    except asyncio.CancelledError:
        crud.update_project(db, project_id, status="failed",
                           error_message="Server reloaded during analysis. Please restart analysis.")
        crud.add_log(db, project_id,
                    "Analysis interrupted: server reloaded. Re-start from Dashboard to continue.",
                    "error")
    except Exception as e:
        error_msg = str(e)[:500]
        crud.update_project(db, project_id, status="failed", error_message=error_msg)
        crud.add_log(db, project_id, f"Analysis failed: {error_msg}", "error")
        if project_id in _sse_queues:
            try:
                _sse_queues[project_id].put_nowait({
                    "type": "error",
                    "message": f"Analysis failed: {error_msg}",
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception:
                pass
    finally:
        cleanup_project(project_id)
        _analysis_tasks.pop(project_id, None)
        db.close()


@app.post("/api/projects/{project_id}/pause", tags=["Analysis"])
async def pause_analysis(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Pause ongoing analysis."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    from backend.agents.agent_nodes import pause_project
    pause_project(project_id)

    crud.update_project(db, project_id, status="paused")
    crud.add_log(db, project_id, "Analysis paused by user", "milestone", "system")

    return {"message": "Analysis paused", "project_id": project_id}


@app.post("/api/projects/{project_id}/resume", tags=["Analysis"])
async def resume_analysis(
    project_id: str,
    resume_data: ResumeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Resume paused analysis with optional context injection."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    from backend.agents.agent_nodes import resume_project
    resume_project(project_id, resume_data.context)

    crud.update_project(db, project_id, status="analyzing")
    msg = "Analysis resumed"
    if resume_data.context:
        msg += f" with context: {resume_data.context[:100]}"
        crud.add_log(db, project_id, f"User added context: {resume_data.context[:200]}", "info", "user")

    crud.add_log(db, project_id, "Analysis resumed by user", "milestone", "system")

    return {"message": msg, "project_id": project_id}


@app.post("/api/projects/{project_id}/context", tags=["Analysis"])
async def add_context(
    project_id: str,
    context_data: UserContextRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add user context to ongoing or paused analysis."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    from backend.agents.agent_nodes import add_user_context
    add_user_context(project_id, context_data.context)

    crud.add_log(db, project_id, f"User context added: {context_data.context[:200]}", "info", "user")

    return {"message": "Context added to analysis", "context": context_data.context}


# REAL-TIME UPDATES (SSE)
@app.get("/api/projects/{project_id}/stream", tags=["Analysis"])
async def stream_progress(
    project_id: str,
    request: Request,
    token: str = "",
    db: Session = Depends(get_db)
):
    """Server-Sent Events endpoint for real-time progress updates."""
    # Manual auth check for SSE (headers not easily passed in EventSource)
    from backend.auth import decode_token
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    async def event_generator():
        queue = _sse_queues.get(project_id)
        # Send initial heartbeat
        yield f"data: {json.dumps({'type': 'connected', 'project_id': project_id})}\n\n"

        while True:
            if await request.is_disconnected():
                break

            if queue:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in ("complete", "error"):
                        break
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"data: {json.dumps({'type': 'heartbeat', 'ts': time.time()})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'heartbeat', 'ts': time.time()})}\n\n"
                await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/projects/{project_id}/logs", response_model=List[LogOut], tags=["Analysis"])
async def get_logs(
    project_id: str,
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get analysis logs for a project."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    logs = crud.get_project_logs(db, project_id, limit=limit)
    return logs


# DOCUMENTATION
@app.get("/api/projects/{project_id}/documents", tags=["Documentation"])
async def get_documents(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all documentation for a project."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    docs = crud.get_project_documents(db, project_id)
    return [DocumentOut.model_validate(d) for d in docs]


@app.get("/api/projects/{project_id}/documents/{persona}", tags=["Documentation"])
async def get_document_by_persona(
    project_id: str,
    persona: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get documentation for specific persona (sde or pm)."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    doc = crud.get_document_by_persona(db, project_id, persona)
    if not doc:
        raise HTTPException(status_code=404, detail=f"No {persona.upper()} documentation found")
    return DocumentOut.model_validate(doc)


@app.get("/api/projects/{project_id}/diagrams", tags=["Documentation"])
async def get_diagrams(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all generated diagrams."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    diagrams = crud.get_project_diagrams(db, project_id)
    return [DiagramOut.model_validate(d) for d in diagrams]


# Q&A
@app.post("/api/projects/{project_id}/qa", response_model=QAResponse, tags=["Q&A"])
async def ask_question(
    project_id: str,
    qa_request: QARequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Ask a question about the analyzed codebase."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    if project.status == "created":
        raise HTTPException(status_code=400, detail="Analysis not started yet")

    from backend.agents.agent_nodes import qa_agent

    # Get project summary
    project_context = _project_summaries.get(project_id, {
        "repo_type": project.repo_type or "Unknown",
        "api_endpoints": [],
        "tech_stack": [],
        "key_features": [],
        "db_models": [],
        "auth_patterns": []
    })

    result = await qa_agent(
        project_id=project_id,
        question=qa_request.question,
        persona=qa_request.persona,
        project_context=project_context
    )

    # Save Q&A to history
    crud.save_qa(
        db, project_id,
        persona=qa_request.persona,
        question=qa_request.question,
        answer=result["answer"],
        sources=result.get("sources", [])
    )

    return QAResponse(**result)


@app.get("/api/projects/{project_id}/qa/history", tags=["Q&A"])
async def get_qa_history(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get Q&A history for a project."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    entries = crud.get_project_qa(db, project_id)
    return [QAEntryOut.model_validate(e) for e in entries]


# EXPORT
@app.get("/api/projects/{project_id}/export/markdown", tags=["Export"])
async def export_markdown(
    project_id: str,
    persona: str = "both",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export documentation as Markdown."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    content = f"# {project.name} - Documentation\n\n"
    content += f"*Generated on {datetime.now().strftime('%B %d, %Y')}*\n\n---\n\n"

    if persona in ("sde", "both"):
        sde_doc = crud.get_document_by_persona(db, project_id, "sde")
        if sde_doc:
            content += "# Software Engineer (SDE) Documentation\n\n"
            content += sde_doc.content
            content += "\n\n---\n\n"

    if persona in ("pm", "both"):
        pm_doc = crud.get_document_by_persona(db, project_id, "pm")
        if pm_doc:
            content += "# Product Manager (PM) Documentation\n\n"
            content += pm_doc.content
            content += "\n\n---\n\n"

    diagrams = crud.get_project_diagrams(db, project_id)
    if diagrams:
        content += "# Visual Diagrams\n\n"
        for diagram in diagrams:
            content += f"## {diagram.title}\n\n"
            content += f"{diagram.description}\n\n"
            content += f"```mermaid\n{diagram.mermaid_code}\n```\n\n"

    # Save to temp file
    tmp_path = UPLOADS_DIR / project_id / f"{project.name}_docs.md"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_text(content, encoding="utf-8")

    return FileResponse(
        str(tmp_path),
        media_type="text/markdown",
        filename=f"{project.name}_documentation.md"
    )


@app.get("/api/projects/{project_id}/export/pdf", tags=["Export"])
async def export_pdf(
    project_id: str,
    persona: str = "both",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export documentation as PDF."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    from backend.utils.pdf_exporter import export_full_documentation

    sde_doc = crud.get_document_by_persona(db, project_id, "sde")
    pm_doc = crud.get_document_by_persona(db, project_id, "pm")
    diagrams = crud.get_project_diagrams(db, project_id)

    diagrams_data = [{"title": d.title, "description": d.description, "mermaid_code": d.mermaid_code}
                     for d in diagrams]

    output_path = str(UPLOADS_DIR / project_id / f"{project.name}_docs.pdf")
    (UPLOADS_DIR / project_id).mkdir(parents=True, exist_ok=True)

    try:
        export_full_documentation(
            project_name=project.name,
            sde_content=sde_doc.content if sde_doc and persona in ("sde", "both") else None,
            pm_content=pm_doc.content if pm_doc and persona in ("pm", "both") else None,
            diagrams=diagrams_data,
            output_path=output_path
        )
        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename=f"{project.name}_documentation.pdf"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export failed: {str(e)}")


# AGENT TRACES (Observability)
@app.get("/api/projects/{project_id}/traces", tags=["Observability"])
async def get_traces(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get agent execution traces for a project (Langfuse-compatible)."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    traces = crud.get_project_traces(db, project_id)
    return [AgentTraceOut.model_validate(t) for t in traces]


# ADMIN ROUTES
@app.get("/api/admin/stats", tags=["Admin"])
async def admin_stats(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get system-wide statistics (admin only)."""
    return crud.get_admin_stats(db)


@app.get("/api/admin/users", tags=["Admin"])
async def list_all_users(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """List all users (admin only)."""
    users = crud.get_all_users(db)
    return [UserOut.model_validate(u) for u in users]


@app.get("/api/admin/users/{user_id}", response_model=UserOut, tags=["Admin"])
async def get_user(
    user_id: str,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.put("/api/admin/users/{user_id}", response_model=UserOut, tags=["Admin"])
async def update_user(
    user_id: str,
    update_data: UserAdminUpdate,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update user (admin only)."""
    updates = {k: v for k, v in update_data.model_dump().items() if v is not None}
    user = crud.update_user(db, user_id, **updates)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.delete("/api/admin/users/{user_id}", tags=["Admin"])
async def delete_user(
    user_id: str,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Delete user and all their projects (admin only)."""
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    success = crud.delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}


@app.get("/api/admin/projects", tags=["Admin"])
async def list_all_projects(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """List all projects across all users (admin only)."""
    projects = crud.get_all_projects(db)
    return [ProjectOut.model_validate(p) for p in projects]


@app.delete("/api/admin/projects/{project_id}", tags=["Admin"])
async def admin_delete_project(
    project_id: str,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Delete any project (admin only)."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project_id in _analysis_tasks:
        _analysis_tasks[project_id].cancel()

    upload_dir = UPLOADS_DIR / project_id
    shutil.rmtree(upload_dir, ignore_errors=True)

    try:
        from backend.utils.vector_store import CodeVectorStore
        CodeVectorStore(project_id).delete_collection()
    except Exception:
        pass

    crud.delete_project(db, project_id)
    return {"message": "Project deleted"}


# SEARCH (semantic code search)
@app.get("/api/projects/{project_id}/search", tags=["Search"])
async def search_code(
    project_id: str,
    q: str,
    n: int = 5,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Semantic code search across project chunks."""
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    if project.status == "created":
        raise HTTPException(status_code=400, detail="Analysis not run yet")

    from backend.utils.vector_store import CodeVectorStore
    store = CodeVectorStore(project_id)
    results = store.search(q, n_results=min(n, 10))

    return {"query": q, "results": results, "count": len(results)}


# HEALTH CHECK
@app.get("/health", tags=["System"])
async def health_check():
    """System health check."""
    return {
        "status": "healthy",
        "service": "Multi-Agent Code Analysis System",
        "version": "1.0.0",
        "active_analyses": len(_analysis_tasks)
    }


@app.get("/", tags=["System"])
async def root():
    return {
        "message": "Multi-Agent Code Analysis & Documentation System",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health"
    }
