"""
LangGraph Agent Nodes - 7 specialized agents.
Each agent has a single, well-defined responsibility.
"""
import os
import re
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from backend.agents.state import AnalysisState
from backend.config import (
    OPENAI_API_KEY, ANTHROPIC_API_KEY, LLM_MODEL, LLM_PROVIDER,
    LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
)

# Global pause control
# Maps project_id -> asyncio.Event (set = running, clear = paused)
_pause_events: Dict[str, asyncio.Event] = {}
_user_contexts: Dict[str, List[str]] = {}
_progress_callbacks: Dict[str, Any] = {}  # project_id -> callable


def register_project(project_id: str):
    """Register a new project for analysis control."""
    event = asyncio.Event()
    event.set()  # Running by default
    _pause_events[project_id] = event
    _user_contexts[project_id] = []


def pause_project(project_id: str):
    """Pause analysis for a project."""
    if project_id in _pause_events:
        _pause_events[project_id].clear()


def resume_project(project_id: str, context: str = ""):
    """Resume analysis for a project, optionally with added context."""
    if project_id in _pause_events:
        _pause_events[project_id].set()
    if context and project_id in _user_contexts:
        _user_contexts[project_id].append(context)


def add_user_context(project_id: str, context: str):
    """Add user context to ongoing analysis."""
    if project_id not in _user_contexts:
        _user_contexts[project_id] = []
    _user_contexts[project_id].append(context)


def set_progress_callback(project_id: str, callback):
    """Set a callback for progress updates."""
    _progress_callbacks[project_id] = callback


def cleanup_project(project_id: str):
    """Clean up project state after analysis."""
    _pause_events.pop(project_id, None)
    _user_contexts.pop(project_id, None)
    _progress_callbacks.pop(project_id, None)


async def _wait_if_paused(project_id: str):
    """Wait while analysis is paused."""
    if project_id in _pause_events:
        await _pause_events[project_id].wait()


async def _emit_progress(project_id: str, message: str, progress: int,
                          level: str = "info", agent: str = "system"):
    """Emit a progress update."""
    callback = _progress_callbacks.get(project_id)
    if callback:
        await callback(project_id, message, progress, level, agent)


# LLM Factory
def get_llm(temperature: float = 0.3) -> BaseChatModel:
    """Create LLM instance based on configuration."""
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=LLM_MODEL or "claude-3-haiku-20240307",
            api_key=ANTHROPIC_API_KEY,
            temperature=temperature,
            max_tokens=4096
        )
    elif OPENAI_API_KEY:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=LLM_MODEL or "gpt-4o-mini",
            api_key=OPENAI_API_KEY,
            temperature=temperature,
            max_tokens=4096
        )
    else:
        raise ValueError(
            "No LLM API key configured. Please set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env"
        )


def _track_usage(state: AnalysisState, agent_name: str, response, start_time: float) -> dict:
    """Extract token usage from LLM response."""
    latency_ms = int((time.time() - start_time) * 1000)
    usage = {}
    try:
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = {
                "agent_name": agent_name,
                "input_tokens": response.usage_metadata.get("input_tokens", 0),
                "output_tokens": response.usage_metadata.get("output_tokens", 0),
                "latency_ms": latency_ms
            }
        elif hasattr(response, "response_metadata"):
            meta = response.response_metadata
            tok = meta.get("token_usage", meta.get("usage", {}))
            usage = {
                "agent_name": agent_name,
                "input_tokens": tok.get("prompt_tokens", tok.get("input_tokens", 0)),
                "output_tokens": tok.get("completion_tokens", tok.get("output_tokens", 0)),
                "latency_ms": latency_ms
            }
    except Exception:
        pass
    return usage or {"agent_name": agent_name, "input_tokens": 0, "output_tokens": 0, "latency_ms": latency_ms}


# AGENT 1: File Structure Agent
# Responsibility: Walk file tree, detect repo type, identify important files
async def file_structure_agent(state: AnalysisState) -> Dict[str, Any]:
    project_id = state["project_id"]
    await _wait_if_paused(project_id)
    await _emit_progress(project_id, "Agent 1/7: Analyzing file structure and repository type...", 5, "info", "FileStructureAgent")

    from backend.utils.file_processor import get_file_tree, get_important_files, detect_repo_type

    repo_path = state["repo_path"]

    try:
        # Build file tree
        await _emit_progress(project_id, "Building repository file tree...", 8, "info", "FileStructureAgent")
        file_tree = get_file_tree(repo_path)

        # Get important files
        await _emit_progress(project_id, "Identifying important files and entry points...", 12, "info", "FileStructureAgent")
        important_files = get_important_files(repo_path)

        # Detect repo type
        repo_type, entry_points, dependencies = detect_repo_type(repo_path, important_files)

        # Extract config files
        config_exts = {".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".env"}
        config_files = [
            f["rel_path"] for f in important_files
            if f["ext"] in config_exts or f["name"].lower() in
            {"package.json", "requirements.txt", "dockerfile", "docker-compose.yml",
             "pyproject.toml", "setup.py", ".env.example", "go.mod", "cargo.toml"}
        ][:15]

        total_files = len(important_files)

        await _emit_progress(
            project_id,
            f"Detected: {repo_type} | Entry points: {len(entry_points)} | Files: {total_files}",
            15, "milestone", "FileStructureAgent"
        )

        return {
            "repo_type": repo_type,
            "entry_points": entry_points,
            "config_files": config_files,
            "dependencies": dependencies,
            "file_tree": file_tree,
            "important_files": important_files,
            "total_files": total_files,
            "current_agent": "FileStructureAgent",
            "progress": 15,
            "messages": [f"Repository type detected: {repo_type}"]
        }

    except Exception as e:
        return {
            "errors": [f"FileStructureAgent error: {str(e)}"],
            "repo_type": "Unknown",
            "entry_points": [],
            "config_files": [],
            "dependencies": {},
            "file_tree": {},
            "important_files": [],
            "total_files": 0,
            "current_agent": "FileStructureAgent",
            "progress": 15,
            "messages": [f"File structure analysis failed: {str(e)}"]
        }


# AGENT 2: Code Chunking Agent
# Responsibility: Read files, chunk by functions/classes, index in ChromaDB
async def code_chunking_agent(state: AnalysisState) -> Dict[str, Any]:
    project_id = state["project_id"]
    await _wait_if_paused(project_id)
    await _emit_progress(project_id, "Agent 2/7: Chunking code and building semantic index...", 16, "info", "CodeChunkingAgent")

    from backend.utils.code_chunker import chunk_file
    from backend.utils.vector_store import CodeVectorStore
    from backend.config import BINARY_EXTENSIONS

    important_files = state.get("important_files", [])
    store = CodeVectorStore(project_id)

    all_chunks = []
    total = len(important_files)
    processed = 0

    for i, file_info in enumerate(important_files[:100]):  # Cap at 100 files
        await _wait_if_paused(project_id)

        file_path = file_info["path"]
        rel_path = file_info["rel_path"]
        ext = file_info["ext"]

        if ext in BINARY_EXTENSIONS:
            await _emit_progress(project_id, f"Skipped binary file: {rel_path}", 16, "warning", "CodeChunkingAgent")
            continue

        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue

            chunks = chunk_file(rel_path, content)
            all_chunks.extend(chunks)

            processed += 1
            progress = 16 + int((i / max(total, 1)) * 24)

            if i % 5 == 0 or file_info.get("priority"):
                await _emit_progress(
                    project_id,
                    f"Processing file {i+1}/{min(total, 100)}: {rel_path}",
                    progress, "info", "CodeChunkingAgent"
                )

        except Exception as e:
            await _emit_progress(project_id, f"Error processing {rel_path}: {str(e)}", 16, "warning", "CodeChunkingAgent")

    # Index in ChromaDB
    await _emit_progress(project_id, f"Building semantic search index ({len(all_chunks)} chunks)...", 38, "info", "CodeChunkingAgent")

    stored = 0
    if all_chunks:
        stored = store.add_chunks(all_chunks)

    await _emit_progress(
        project_id,
        f"Code indexing complete: {stored} chunks indexed from {processed} files",
        40, "milestone", "CodeChunkingAgent"
    )

    return {
        "all_chunks": all_chunks[:500],  # Keep in state for agents
        "total_chunks": len(all_chunks),
        "current_agent": "CodeChunkingAgent",
        "progress": 40,
        "messages": [f"Indexed {stored} code chunks from {processed} files for semantic search"]
    }


# AGENT 3: API & Architecture Extractor Agent
# Responsibility: Extract API endpoints, DB schemas, auth patterns via LLM
async def api_extractor_agent(state: AnalysisState) -> Dict[str, Any]:
    project_id = state["project_id"]
    await _wait_if_paused(project_id)
    await _emit_progress(project_id, "Agent 3/7: Extracting API endpoints, database models, and architecture...", 41, "info", "APIExtractorAgent")

    from backend.utils.code_chunker import extract_api_info, extract_db_models

    important_files = state.get("important_files", [])
    all_chunks = state.get("all_chunks", [])

    # Static extraction (no LLM needed)
    api_endpoints = []
    db_models = []

    for file_info in important_files[:50]:
        try:
            content = Path(file_info["path"]).read_text(encoding="utf-8", errors="ignore")
            endpoints = extract_api_info(content, file_info["rel_path"])
            api_endpoints.extend(endpoints)
            models = extract_db_models(content, file_info["rel_path"])
            db_models.extend(models)
        except Exception:
            pass

    # LLM-based extraction for deeper analysis
    await _emit_progress(project_id, "Using AI to analyze architecture patterns and business logic...", 45, "info", "APIExtractorAgent")

    auth_patterns = []
    business_logic = []
    tech_stack = [state.get("repo_type", "Unknown")]
    key_features = []

    try:
        llm = get_llm(temperature=0.1)

        # Build context from key files
        context_chunks = []
        for chunk in all_chunks[:20]:
            content = chunk.get("content", "")
            file_path = chunk.get("metadata", {}).get("file_path", "") if isinstance(chunk.get("metadata"), dict) else chunk.get("file_path", "")
            if content:
                context_chunks.append(f"File: {file_path}\n```\n{content[:500]}\n```")

        context = "\n\n".join(context_chunks[:10])
        user_contexts = _user_contexts.get(project_id, [])
        extra_ctx = "\n".join(f"User note: {c}" for c in user_contexts) if user_contexts else ""

        start_time = time.time()
        prompt = f"""Analyze this codebase and extract:
1. Authentication/authorization patterns (list them)
2. Key business logic areas (list them)
3. Technology stack components (list them)
4. Key product features for end users (list them)

Repo type: {state.get('repo_type', 'Unknown')}
API endpoints found: {len(api_endpoints)}
Database models found: {len(db_models)}

Code samples:
{context[:3000]}

{extra_ctx}

Respond in this exact JSON format:
{{
  "auth_patterns": ["pattern1", "pattern2"],
  "business_logic": ["area1", "area2"],
  "tech_stack": ["tech1", "tech2"],
  "key_features": ["feature1", "feature2"]
}}"""

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        usage = _track_usage(state, "APIExtractorAgent", response, start_time)

        # Parse JSON response
        content = response.content
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            import json
            try:
                data = json.loads(json_match.group())
                auth_patterns = data.get("auth_patterns", [])[:10]
                business_logic = data.get("business_logic", [])[:10]
                tech_stack.extend(data.get("tech_stack", []))
                key_features = data.get("key_features", [])[:15]
            except json.JSONDecodeError:
                pass

    except Exception as e:
        usage = {"agent_name": "APIExtractorAgent", "input_tokens": 0, "output_tokens": 0, "latency_ms": 0}
        await _emit_progress(project_id, f"LLM extraction note: {str(e)[:100]}", 48, "warning", "APIExtractorAgent")

    await _emit_progress(
        project_id,
        f"Found {len(api_endpoints)} API endpoints, {len(db_models)} DB models, {len(key_features)} features",
        50, "milestone", "APIExtractorAgent"
    )

    return {
        "api_endpoints": api_endpoints[:50],
        "db_models": db_models[:30],
        "auth_patterns": auth_patterns,
        "business_logic": business_logic,
        "tech_stack": list(set(tech_stack))[:20],
        "key_features": key_features,
        "current_agent": "APIExtractorAgent",
        "progress": 50,
        "trace_data": [usage],
        "messages": [f"Architecture analysis complete: {len(api_endpoints)} endpoints, {len(db_models)} models"]
    }


# AGENT 4: Web Search Agent
# Responsibility: Search for latest best practices, security guidelines online
async def web_search_agent(state: AnalysisState) -> Dict[str, Any]:
    project_id = state["project_id"]
    await _wait_if_paused(project_id)

    if not state.get("web_search_enabled", True):
        await _emit_progress(project_id, "Web search disabled, skipping...", 55, "info", "WebSearchAgent")
        return {"web_findings": {}, "current_agent": "WebSearchAgent", "progress": 55, "messages": ["Web search skipped"]}

    await _emit_progress(project_id, "Agent 4/7: Searching web for latest best practices...", 51, "info", "WebSearchAgent")

    web_findings = {}
    repo_type = state.get("repo_type", "")
    tech_stack = state.get("tech_stack", [])

    search_topics = []

    # Build search queries based on detected tech
    if "FastAPI" in repo_type or "FastAPI" in str(tech_stack):
        search_topics.append(("FastAPI best practices 2024", "fastapi_practices"))
    if "Django" in repo_type or "Django" in str(tech_stack):
        search_topics.append(("Django REST API best practices", "django_practices"))
    if "React" in str(tech_stack) or "Next.js" in str(tech_stack):
        search_topics.append(("React Next.js architecture patterns 2024", "react_patterns"))
    if "SQLAlchemy" in str(tech_stack):
        search_topics.append(("SQLAlchemy session management best practices", "sqlalchemy_patterns"))

    # Always add security
    search_topics.append(("API security authentication OWASP best practices", "security_practices"))

    if not search_topics:
        lang = repo_type.split("(")[0].strip() if "(" in repo_type else repo_type
        search_topics.append((f"{lang} web development best practices 2024", "general_practices"))

    try:
        from langchain_community.tools import DuckDuckGoSearchRun
        search_tool = DuckDuckGoSearchRun()

        for i, (query, key) in enumerate(search_topics[:4]):
            await _wait_if_paused(project_id)
            progress = 51 + int((i / len(search_topics[:4])) * 8)
            await _emit_progress(
                project_id,
                f'Searching: "{query}"',
                progress, "info", "WebSearchAgent"
            )
            try:
                result = search_tool.run(query)
                web_findings[key] = result[:1500] if result else ""
                await asyncio.sleep(0.5)  # Rate limiting
            except Exception as e:
                web_findings[key] = f"Search unavailable: {str(e)[:100]}"

    except Exception as e:
        await _emit_progress(project_id, f"Web search unavailable: {str(e)[:100]}", 58, "warning", "WebSearchAgent")
        web_findings["note"] = "Web search was unavailable. Documentation generated from code analysis only."

    await _emit_progress(
        project_id,
        f"Web research complete: {len(web_findings)} topic areas researched",
        60, "milestone", "WebSearchAgent"
    )

    return {
        "web_findings": web_findings,
        "current_agent": "WebSearchAgent",
        "progress": 60,
        "messages": [f"Web research completed: {len(web_findings)} topics"]
    }


# AGENT 5: SDE Documentation Agent
# Responsibility: Generate comprehensive technical SDE documentation
async def sde_doc_agent(state: AnalysisState) -> Dict[str, Any]:
    project_id = state["project_id"]
    await _wait_if_paused(project_id)

    if "sde" not in state.get("personas", ["sde"]):
        return {"sde_report": "", "current_agent": "SDEDocAgent", "progress": 75, "messages": ["SDE docs skipped"]}

    await _emit_progress(project_id, "Agent 5/7: Generating Software Engineer (SDE) documentation...", 61, "info", "SDEDocAgent")

    try:
        llm = get_llm(temperature=0.2)

        # Prepare context
        api_endpoints = state.get("api_endpoints", [])
        db_models = state.get("db_models", [])
        auth_patterns = state.get("auth_patterns", [])
        tech_stack = state.get("tech_stack", [])
        entry_points = state.get("entry_points", [])
        config_files = state.get("config_files", [])
        web_findings = state.get("web_findings", {})
        repo_type = state.get("repo_type", "Unknown")
        total_files = state.get("total_files", 0)
        total_chunks = state.get("total_chunks", 0)
        key_features = state.get("key_features", [])
        user_contexts = _user_contexts.get(project_id, [])
        depth = state.get("analysis_depth", "standard")

        # Build context
        endpoints_str = "\n".join([
            f"  - {e.get('method', 'GET')} {e.get('path', '/')} (in {e.get('file', '')})"
            for e in api_endpoints[:20]
        ]) or "  No API endpoints detected"

        models_str = "\n".join([
            f"  - {m.get('name', 'Model')} ({len(m.get('fields', []))} fields)"
            for m in db_models[:15]
        ]) or "  No database models detected"

        web_ctx = "\n".join([f"**{k}**: {v[:300]}" for k, v in list(web_findings.items())[:2]])
        user_ctx = "\n".join(f"- {c}" for c in user_contexts) if user_contexts else ""

        verbosity_instruction = {
            "low": "Be concise. Use bullet points. Max 800 words total.",
            "medium": "Provide thorough documentation with examples. Aim for 1200-2000 words.",
            "high": "Be comprehensive and detailed. Include code examples and edge cases. Aim for 2500+ words."
        }.get(state.get("verbosity", "medium"), "")

        start_time = time.time()
        prompt = f"""Generate professional Software Engineer (SDE) documentation for this codebase.

## Repository Information
- Type: {repo_type}
- Total files analyzed: {total_files}
- Code sections indexed: {total_chunks}
- Entry Points: {', '.join(entry_points[:5]) or 'Not detected'}
- Config Files: {', '.join(config_files[:5]) or 'None'}

## Technology Stack
{chr(10).join(f'- {t}' for t in tech_stack[:15])}

## API Endpoints ({len(api_endpoints)} found)
{endpoints_str}

## Database Models ({len(db_models)} found)
{models_str}

## Authentication Patterns
{chr(10).join(f'- {p}' for p in auth_patterns[:8]) or '- Not detected'}

## Best Practices Research
{web_ctx[:600]}

{"## User Provided Context" + chr(10) + user_ctx if user_ctx else ""}

## Instructions
{verbosity_instruction}

Generate COMPLETE SDE documentation with ALL these sections:

# Technical Architecture Overview
[Describe system architecture, component relationships, design patterns]

## System Components
[List and describe main components]

## Architecture Diagram Description
[Describe how components interact]

# API Documentation
[Document all detected endpoints with methods, paths, expected inputs/outputs]

# Database Schema & Data Models
[Document all detected models with fields and relationships]

# Code Structure & Module Dependencies
[Explain folder/module organization]

# Setup & Deployment Guide
## Prerequisites
## Installation Steps
## Environment Configuration
## Running the Application
## Docker/Deployment (if applicable)

# Authentication & Security
[Document auth flows, security patterns, best practices]

# Error Handling Patterns
[Document error handling strategies]

# Performance Considerations
[Document caching, optimization opportunities, known bottlenecks]

# Development Guidelines
[Coding standards, testing approach, contribution guide]

Make the documentation clear, technical, and actionable for software engineers.
Use proper Markdown formatting with headers, code blocks, and bullet points."""

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        usage = _track_usage(state, "SDEDocAgent", response, start_time)
        sde_report = response.content

        await _emit_progress(project_id, "SDE documentation generated successfully", 75, "milestone", "SDEDocAgent")

        return {
            "sde_report": sde_report,
            "current_agent": "SDEDocAgent",
            "progress": 75,
            "trace_data": [usage],
            "messages": ["SDE documentation generated"]
        }

    except Exception as e:
        fallback = _generate_fallback_sde_doc(state)
        await _emit_progress(project_id, f"SDE doc generation note: {str(e)[:100]}", 75, "warning", "SDEDocAgent")
        return {
            "sde_report": fallback,
            "current_agent": "SDEDocAgent",
            "progress": 75,
            "errors": [f"SDEDocAgent LLM error: {str(e)}"],
            "messages": ["SDE documentation generated (from analysis data)"]
        }


def _generate_fallback_sde_doc(state: AnalysisState) -> str:
    """Generate basic SDE doc from extracted data without LLM."""
    repo_type = state.get("repo_type", "Unknown")
    api_endpoints = state.get("api_endpoints", [])
    db_models = state.get("db_models", [])
    tech_stack = state.get("tech_stack", [])
    entry_points = state.get("entry_points", [])

    doc = f"""# Technical Architecture Overview

## Repository Type
{repo_type}

## Technology Stack
{chr(10).join(f'- {t}' for t in tech_stack) or '- Not detected'}

## Entry Points
{chr(10).join(f'- `{e}`' for e in entry_points) or '- Not detected'}

# API Documentation

## Detected Endpoints ({len(api_endpoints)})

"""
    for ep in api_endpoints[:20]:
        doc += f"### `{ep.get('method', 'GET')} {ep.get('path', '/')}`\n"
        doc += f"- File: `{ep.get('file', 'Unknown')}`\n"
        doc += f"- Line: {ep.get('line', '?')}\n\n"

    doc += f"""
# Database Schema

## Detected Models ({len(db_models)})

"""
    for model in db_models[:15]:
        doc += f"### {model.get('name', 'Model')}\n"
        for field in model.get("fields", [])[:10]:
            doc += f"- `{field.get('name', 'field')}`: {field.get('definition', '')}\n"
        doc += "\n"

    doc += """
# Setup & Deployment

## Prerequisites
- Review the repository's README for specific requirements
- Ensure all dependencies are installed

## Installation
```bash
# Clone the repository
git clone <repo-url>
cd <repo-directory>

# Install dependencies (Python)
pip install -r requirements.txt

# Install dependencies (Node.js)
npm install
```

# Development Guidelines
- Follow existing code patterns and conventions
- Write tests for new functionality
- Document public APIs and complex logic
"""
    return doc


# AGENT 6: PM Documentation Agent
# Responsibility: Generate business-focused PM documentation
async def pm_doc_agent(state: AnalysisState) -> Dict[str, Any]:
    project_id = state["project_id"]
    await _wait_if_paused(project_id)

    if "pm" not in state.get("personas", ["sde"]):
        return {"pm_report": "", "current_agent": "PMDocAgent", "progress": 85, "messages": ["PM docs skipped"]}

    await _emit_progress(project_id, "Agent 6/7: Generating Product Manager (PM) documentation...", 76, "info", "PMDocAgent")

    try:
        llm = get_llm(temperature=0.3)

        api_endpoints = state.get("api_endpoints", [])
        key_features = state.get("key_features", [])
        business_logic = state.get("business_logic", [])
        tech_stack = state.get("tech_stack", [])
        repo_type = state.get("repo_type", "Unknown")
        total_files = state.get("total_files", 0)
        web_findings = state.get("web_findings", {})
        user_contexts = _user_contexts.get(project_id, [])
        verbosity = state.get("verbosity", "medium")

        features_str = "\n".join(f"- {f}" for f in key_features[:15]) or "- To be analyzed from codebase"
        logic_str = "\n".join(f"- {l}" for l in business_logic[:10]) or "- Various business processes"
        user_ctx = "\n".join(f"- {c}" for c in user_contexts) if user_contexts else ""

        verbosity_instruction = {
            "low": "Be concise. Focus on key points. Max 800 words.",
            "medium": "Provide clear business documentation. Aim for 1200-1800 words.",
            "high": "Be thorough. Include all business context, use cases, and strategic implications. 2000+ words."
        }.get(verbosity, "")

        start_time = time.time()
        prompt = f"""Generate professional Product Manager (PM) documentation for this product/codebase.

## Repository Information
- Type: {repo_type}
- Files analyzed: {total_files}
- API surface: {len(api_endpoints)} endpoints

## Detected Features
{features_str}

## Business Logic Areas
{logic_str}

## Technology Components (simplified for PM)
{chr(10).join(f'- {t}' for t in tech_stack[:10])}

{"## Team Context" + chr(10) + user_ctx if user_ctx else ""}

## Instructions
{verbosity_instruction}

Write COMPLETE PM documentation in NON-TECHNICAL language.

Base the Feature Inventory strictly on the Detected Features and Business Logic listed above.
Do not invent or add generic features that are not in the detected list.
If a feature section has nothing to say, write "Not detected in this codebase."

Required sections (write all of them):

# Product Overview
[What does this product actually do, based on detected endpoints and features?]

## Product Mission
[Core purpose derived from the actual detected functionality]

## Target Users
[Who realistically uses this product, based on what it actually does]

# Feature Inventory

## Core Features
[List ONLY detected features from the 'Detected Features' section above, explained in plain language]

## Supporting Features
[Any secondary features detected in Business Logic, or: 'Not detected in this codebase.']

## Admin Features
[Any admin/management capabilities detected, or: 'Not detected in this codebase.']

# User Journey Flows

## Primary User Journey
[Walk through the main use case based on actual detected API endpoints]

## Additional Journeys
[Other key user flows from detected endpoints, if any]

# Business Rules & Logic
[Business rules from the detected logic areas listed above]

# Integration Points
[Only integrations actually detected in the codebase, e.g. third-party libs, APIs called]

# Data & Analytics Capabilities
[Only data capabilities that actually exist in the codebase]

# Technical Constraints & Limitations
[Real constraints based on what was found, in business-friendly language]

# Roadmap Implications
[Based on current architecture: what features would be easy vs hard to add]

Use plain English. A non-technical PM should be able to read this and accurately describe the product."""

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        usage = _track_usage(state, "PMDocAgent", response, start_time)
        pm_report = response.content

        await _emit_progress(project_id, "PM documentation generated successfully", 85, "milestone", "PMDocAgent")

        return {
            "pm_report": pm_report,
            "current_agent": "PMDocAgent",
            "progress": 85,
            "trace_data": [usage],
            "messages": ["PM documentation generated"]
        }

    except Exception as e:
        fallback = _generate_fallback_pm_doc(state)
        await _emit_progress(project_id, f"PM doc generation note: {str(e)[:100]}", 85, "warning", "PMDocAgent")
        return {
            "pm_report": fallback,
            "current_agent": "PMDocAgent",
            "progress": 85,
            "errors": [f"PMDocAgent LLM error: {str(e)}"],
            "messages": ["PM documentation generated (from analysis data)"]
        }


def _generate_fallback_pm_doc(state: AnalysisState) -> str:
    """Generate basic PM doc from extracted data."""
    key_features = state.get("key_features", [])
    business_logic = state.get("business_logic", [])
    repo_type = state.get("repo_type", "")
    api_endpoints = state.get("api_endpoints", [])

    doc = f"""# Product Overview

## What This Product Does
This is a {repo_type} application with {len(api_endpoints)} API endpoints serving business functionality.

## Target Users
- End users interacting with the product features
- Administrators managing the system

# Feature Inventory

## Detected Features
{chr(10).join(f'- {f}' for f in key_features) or '- Feature analysis in progress'}

# Business Logic Areas
{chr(10).join(f'- {l}' for l in business_logic) or '- Business logic documentation pending'}

# User Journey Flows

## Primary User Journey
1. User accesses the application
2. User authenticates (if required)
3. User interacts with core features
4. System processes requests and returns results

# Integration Points
- REST API with {len(api_endpoints)} endpoints
- Database storage for persistent data

# Technical Constraints & Limitations
- Refer to technical documentation for detailed constraints

# Data Capabilities
- Data is stored and managed per configured database models
"""
    return doc


# AGENT 7: Diagram Generation Agent
# Responsibility: Generate 4+ Mermaid diagram types
async def diagram_agent(state: AnalysisState) -> Dict[str, Any]:
    project_id = state["project_id"]
    await _wait_if_paused(project_id)

    if not state.get("generate_diagrams", True):
        return {"diagrams": {}, "current_agent": "DiagramAgent", "progress": 95, "messages": ["Diagrams skipped"]}

    await _emit_progress(project_id, "Agent 7/7: Generating visual Mermaid diagrams...", 86, "info", "DiagramAgent")

    diagrams = {}

    api_endpoints = state.get("api_endpoints", [])
    db_models = state.get("db_models", [])
    tech_stack = state.get("tech_stack", [])
    auth_patterns = state.get("auth_patterns", [])
    repo_type = state.get("repo_type", "Unknown")
    key_features = state.get("key_features", [])
    entry_points = state.get("entry_points", [])

    try:
        llm = get_llm(temperature=0.1)

        # Diagram 1: System Architecture (graph TD)
        await _wait_if_paused(project_id)
        await _emit_progress(project_id, "Generating system architecture diagram...", 87, "info", "DiagramAgent")

        arch_context = f"""
Repo type: {repo_type}
Tech stack: {', '.join(tech_stack[:8])}
Entry points: {', '.join(entry_points[:5])}
API endpoints: {len(api_endpoints)}
DB models: {', '.join([m.get('name', '') for m in db_models[:8]])}
""".strip()

        start_time = time.time()
        response = await llm.ainvoke([HumanMessage(content=f"""Generate a Mermaid system architecture diagram for:
{arch_context}

Rules for VALID Mermaid graph TD syntax:
- Use ONLY: graph TD
- Node IDs must be alphanumeric (A, B, C1, FE, BE, etc.) - NO spaces in IDs
- Node labels in square brackets: A["Label Text"]
- Arrows: A --> B or A --> B["Label"]
- No special characters in IDs
- Keep it simple, max 12 nodes

Example of VALID syntax:
```
graph TD
    Client["Web Client"]
    API["API Server"]
    DB["Database"]
    Auth["Auth Service"]
    Client --> API
    API --> DB
    API --> Auth
    Auth --> DB
```

Generate a diagram showing the main components of this system.
Return ONLY the mermaid code block, nothing else.""")])

        usage1 = _track_usage(state, "DiagramAgent_arch", response, start_time)
        arch_code = _extract_mermaid(response.content)
        arch_code = _fix_mermaid_syntax(arch_code, "graph TD")

        diagrams["architecture"] = {
            "title": "System Architecture",
            "description": "High-level view of system components and their relationships.",
            "mermaid_code": arch_code,
            "persona": "both"
        }

        # Diagram 2: Sequence Diagram
        await _wait_if_paused(project_id)
        await _emit_progress(project_id, "Generating API sequence diagram...", 89, "info", "DiagramAgent")

        # Build endpoint context
        ep_context = "\n".join([
            f"- {e.get('method','GET')} {e.get('path','/')}"
            for e in api_endpoints[:10]
        ]) or "- REST API endpoints"

        start_time = time.time()
        response = await llm.ainvoke([HumanMessage(content=f"""Generate a Mermaid sequence diagram showing the main API request flow for:
{ep_context}

Rules for VALID sequenceDiagram syntax:
- Start with: sequenceDiagram
- Participants: participant Client
- Messages: Client->>Server: message text
- Responses: Server-->>Client: response text
- Notes: Note over Client,Server: text
- Loops: loop description ... end
- Alt: alt case1 ... else case2 ... end

Example:
```
sequenceDiagram
    participant C as Client
    participant A as API
    participant DB as Database
    C->>A: POST /api/login
    A->>DB: Query user
    DB-->>A: User data
    A-->>C: JWT token
    C->>A: GET /api/data (with token)
    A-->>C: Protected data
```

Generate a sequence diagram for the main user flow.
Return ONLY the mermaid code block.""")])

        usage2 = _track_usage(state, "DiagramAgent_seq", response, start_time)
        seq_code = _extract_mermaid(response.content)
        seq_code = _fix_mermaid_syntax(seq_code, "sequenceDiagram")

        diagrams["sequence"] = {
            "title": "Request / Data Flow",
            "description": "Main execution flow through application components.",
            "mermaid_code": seq_code,
            "persona": "sde"
        }

        # Diagram 3: Entity Relationship Diagram
        await _wait_if_paused(project_id)
        await _emit_progress(project_id, "Generating entity relationship diagram...", 91, "info", "DiagramAgent")

        model_context = "\n".join([
            f"- {m.get('name','Entity')}: {', '.join([f.get('name','') for f in m.get('fields',[])[:6]])}"
            for m in db_models[:8]
        ]) or f"- Based on {repo_type} application patterns"

        start_time = time.time()
        response = await llm.ainvoke([HumanMessage(content=f"""Generate a Mermaid ER diagram for this application's data model:
{model_context}

Rules for VALID erDiagram syntax:
- Start with: erDiagram
- Entities in UPPERCASE or PascalCase
- Relationships: ENTITY1 ||--o{{ ENTITY2 : "relationship_name"
- Fields inside curly braces: ENTITY {{ type name }}
- Relationship types: ||--||  ||--|{{  }}|--|{{  }}|--o{{

Example:
```
erDiagram
    USER {{
        string id PK
        string email
        string name
        datetime created_at
    }}
    PROJECT {{
        string id PK
        string user_id FK
        string name
        string status
    }}
    USER ||--o{{ PROJECT : "owns"
```

Generate an ER diagram for the main data entities.
Return ONLY the mermaid code block.""")])

        usage3 = _track_usage(state, "DiagramAgent_er", response, start_time)
        er_code = _extract_mermaid(response.content)
        er_code = _fix_mermaid_syntax(er_code, "erDiagram")

        diagrams["er_diagram"] = {
            "title": "Data Model (Entity Relationship)",
            "description": "Database entities and their relationships.",
            "mermaid_code": er_code,
            "persona": "sde"
        }

        # Diagram 4: User Flow (flowchart)
        await _wait_if_paused(project_id)
        await _emit_progress(project_id, "Generating user journey flow diagram...", 93, "info", "DiagramAgent")

        feature_ctx = "\n".join(f"- {f}" for f in key_features[:8]) or "- Core application features"

        start_time = time.time()
        response = await llm.ainvoke([HumanMessage(content=f"""Generate a Mermaid flowchart showing the user journey through this application:
Key features: {feature_ctx}

Rules for VALID flowchart syntax:
- Start with: flowchart TD
- Nodes: A[Process] or A{{Decision}} or A((Start)) or A>Action]
- Arrows: A --> B or A --> |label| B
- Decision: A{{Condition?}} --> |Yes| B and A{{Condition?}} --> |No| C
- Node IDs: alphanumeric only (no spaces)

Example:
```
flowchart TD
    Start((Start)) --> Login[User Login]
    Login --> Auth{{Authenticated?}}
    Auth --> |Yes| Dashboard[View Dashboard]
    Auth --> |No| Error[Show Error]
    Dashboard --> Feature1[Use Feature]
    Dashboard --> Feature2[Another Feature]
    Feature1 --> End((End))
```

Generate a user journey flow diagram.
Return ONLY the mermaid code block.""")])

        usage4 = _track_usage(state, "DiagramAgent_flow", response, start_time)
        flow_code = _extract_mermaid(response.content)
        flow_code = _fix_mermaid_syntax(flow_code, "flowchart TD")

        diagrams["user_flow"] = {
            "title": "User Journey Flow",
            "description": "Step-by-step flow of key user interactions.",
            "mermaid_code": flow_code,
            "persona": "pm"
        }

        # Diagram 5: Authentication Flow
        await _wait_if_paused(project_id)
        await _emit_progress(project_id, "Generating authentication flow diagram...", 94, "info", "DiagramAgent")

        auth_ctx = "\n".join(f"- {p}" for p in auth_patterns[:5]) or "- Standard authentication"

        start_time = time.time()
        response = await llm.ainvoke([HumanMessage(content=f"""Generate a Mermaid flowchart for the authentication flow:
Auth patterns: {auth_ctx}

Use flowchart LR syntax with these rules:
- Start with: flowchart LR
- Use simple alphanumeric node IDs
- Keep it focused on auth flow

Example:
```
flowchart LR
    A[Client] --> B[Login Request]
    B --> C{{Valid Credentials?}}
    C --> |Yes| D[Generate JWT]
    C --> |No| E[Return 401]
    D --> F[Return Token]
    F --> G[Access Protected Routes]
```

Return ONLY the mermaid code block.""")])

        usage5 = _track_usage(state, "DiagramAgent_auth", response, start_time)
        auth_code = _extract_mermaid(response.content)
        auth_code = _fix_mermaid_syntax(auth_code, "flowchart LR")

        diagrams["auth_flow"] = {
            "title": "Authentication & Security Flow",
            "description": "Authentication and authorization flow.",
            "mermaid_code": auth_code,
            "persona": "sde"
        }

        all_usages = [usage1, usage2, usage3, usage4, usage5]

    except Exception as e:
        await _emit_progress(project_id, f"Diagram generation note: {str(e)[:100]}", 94, "warning", "DiagramAgent")
        # Generate fallback diagrams
        diagrams = _generate_fallback_diagrams(state)
        all_usages = []

    await _emit_progress(
        project_id,
        f"Generated {len(diagrams)} Mermaid diagrams",
        95, "milestone", "DiagramAgent"
    )

    return {
        "diagrams": diagrams,
        "current_agent": "DiagramAgent",
        "progress": 95,
        "trace_data": all_usages,
        "messages": [f"{len(diagrams)} visual diagrams generated"]
    }


def _extract_mermaid(text: str) -> str:
    """Extract Mermaid code from LLM response."""
    # Try code block with mermaid label
    match = re.search(r'```mermaid\s*\n(.*?)```', text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try any code block
    match = re.search(r'```\s*\n(.*?)```', text, re.DOTALL)
    if match:
        content = match.group(1).strip()
        # Check if it looks like mermaid
        if any(content.startswith(kw) for kw in ["graph", "flowchart", "sequenceDiagram", "erDiagram", "classDiagram", "stateDiagram"]):
            return content

    # Return raw text if it starts with mermaid keywords
    text = text.strip()
    if any(text.startswith(kw) for kw in ["graph", "flowchart", "sequenceDiagram", "erDiagram", "classDiagram"]):
        return text

    return text


def _fix_mermaid_syntax(code: str, expected_start: str) -> str:
    """Fix common Mermaid syntax issues."""
    if not code or not code.strip():
        return _get_fallback_diagram(expected_start)

    lines = code.strip().split("\n")
    fixed_lines = []

    for line in lines:
        # Fix node IDs with spaces (e.g., "Web Server" -> WebServer)
        # Only fix in edges, not labels
        fixed_lines.append(line)

    result = "\n".join(fixed_lines)

    # Ensure correct start
    if not any(result.strip().startswith(kw) for kw in
               ["graph", "flowchart", "sequenceDiagram", "erDiagram", "classDiagram", "stateDiagram"]):
        result = expected_start + "\n" + result

    return result


def _get_fallback_diagram(diagram_type: str) -> str:
    """Return a simple fallback diagram when generation fails."""
    if "sequenceDiagram" in diagram_type:
        return """sequenceDiagram
    participant C as Client
    participant A as API Server
    participant D as Database
    C->>A: HTTP Request
    A->>D: Query Data
    D-->>A: Return Results
    A-->>C: JSON Response"""
    elif "erDiagram" in diagram_type:
        return """erDiagram
    USER {
        string id PK
        string email
        string name
    }
    PROJECT {
        string id PK
        string user_id FK
        string name
        string status
    }
    USER ||--o{ PROJECT : "owns" """
    elif "flowchart LR" in diagram_type:
        return """flowchart LR
    A[User] --> B[Login]
    B --> C{Valid?}
    C --> |Yes| D[Access Granted]
    C --> |No| E[Access Denied]"""
    else:
        return """flowchart TD
    A[Client] --> B[API Server]
    B --> C[Database]
    B --> D[Cache]
    A --> E[CDN]"""


def _generate_fallback_diagrams(state: AnalysisState) -> dict:
    """Generate simple fallback diagrams from state data."""
    repo_type = state.get("repo_type", "Application")
    tech_stack = state.get("tech_stack", [])
    api_endpoints = state.get("api_endpoints", [])
    db_models = state.get("db_models", [])

    # Build component list
    components = ["Client"]
    if any("API" in t or "FastAPI" in t or "Flask" in t or "Express" in t for t in tech_stack):
        components.append("APIServer")
    if any("DB" in t or "SQL" in t or "Mongo" in t for t in tech_stack):
        components.append("Database")
    if not components[1:]:
        components.extend(["Server", "Database"])

    arch_lines = ["graph TD"]
    prev = None
    labels = {"Client": "Client Browser", "APIServer": "API Server", "Database": "Database",
               "Server": "Application Server"}
    for comp in components:
        label = labels.get(comp, comp)
        arch_lines.append(f'    {comp}["{label}"]')
        if prev:
            arch_lines.append(f"    {prev} --> {comp}")
        prev = comp

    # ER diagram
    er_lines = ["erDiagram"]
    if db_models:
        for model in db_models[:4]:
            name = re.sub(r'\W+', '', model.get("name", "Entity"))
            er_lines.append(f"    {name} {{")
            for field in model.get("fields", [])[:5]:
                fname = re.sub(r'\W+', '_', field.get("name", "field"))
                er_lines.append(f"        string {fname}")
            er_lines.append("    }")
    else:
        er_lines.extend([
            "    USER {", "        string id PK", "        string email", "    }",
            "    PROJECT {", "        string id PK", "        string user_id FK", "        string name", "    }",
            '    USER ||--o{ PROJECT : "owns"'
        ])

    return {
        "architecture": {
            "title": "System Architecture",
            "description": "High-level view of system components.",
            "mermaid_code": "\n".join(arch_lines),
            "persona": "both"
        },
        "sequence": {
            "title": "Request / Data Flow",
            "description": "Main execution flow through application components.",
            "mermaid_code": _get_fallback_diagram("sequenceDiagram"),
            "persona": "sde"
        },
        "er_diagram": {
            "title": "Data Model (Entity Relationship)",
            "description": "Database entities and their relationships.",
            "mermaid_code": "\n".join(er_lines),
            "persona": "sde"
        },
        "user_flow": {
            "title": "User Journey Flow",
            "description": "Step-by-step flow of key user interactions.",
            "mermaid_code": """flowchart TD
    Start((Start)) --> Login[User Login]
    Login --> Auth{Authenticated?}
    Auth --> |Yes| Dashboard[View Dashboard]
    Auth --> |No| Retry[Retry Login]
    Dashboard --> Feature[Use Features]
    Feature --> Export[Export Results]
    Export --> End((End))""",
            "persona": "pm"
        },
        "auth_flow": {
            "title": "Authentication & Security Flow",
            "description": "Authentication and authorization flow.",
            "mermaid_code": _get_fallback_diagram("flowchart LR"),
            "persona": "sde"
        }
    }


# Q&A Agent (on-demand, not part of main graph)
# Responsibility: Answer questions about the codebase
async def qa_agent(project_id: str, question: str, persona: str,
                   project_context: dict) -> dict:
    """
    Answer questions about the analyzed codebase.
    Primary context: generated SDE/PM documentation (already summarised by LLM —
    richer, cheaper than re-querying raw code chunks).
    Secondary context: top-3 ChromaDB code chunks for specific file references.
    """
    try:
        from backend.utils.vector_store import CodeVectorStore
        from backend.database import SessionLocal
        import backend.crud as crud

        # 1. Load generated documentation as primary context
        doc_context = ""
        db = SessionLocal()
        try:
            # Try the matching persona first, fall back to the other
            for p in (persona, "sde", "pm"):
                doc_obj = crud.get_document_by_persona(db, project_id, p)
                if doc_obj and doc_obj.content:
                    # Truncate to keep within token budget
                    doc_context = doc_obj.content[:4000]
                    break
        finally:
            db.close()

        # 2. Code-chunk search for specific file references
        context_parts = []
        sources = []
        try:
            store = CodeVectorStore(project_id)
            # Fewer chunks needed — doc context carries the heavy lifting
            relevant_chunks = store.search(question, n_results=3)
            for chunk in relevant_chunks:
                content  = chunk.get("content", "")
                meta     = chunk.get("metadata", {})
                file_path = meta.get("file_path", "unknown")
                chunk_type = meta.get("type", "code")
                relevance  = chunk.get("relevance_score", 0)
                if relevance > 0.3:
                    context_parts.append(
                        f"From `{file_path}` ({chunk_type}):\n```\n{content[:400]}\n```"
                    )
                    sources.append({
                        "file": file_path,
                        "type": chunk_type,
                        "relevance": round(relevance, 2)
                    })
        except Exception:
            pass  # Vector store may not be ready; doc context is enough

        # 3. Build prompt
        project_summary = (
            f"Repository: {project_context.get('repo_type', 'Unknown')}  \n"
            f"Endpoints: {len(project_context.get('api_endpoints', []))}  \n"
            f"Stack: {', '.join(project_context.get('tech_stack', [])[:5])}"
        )

        code_context = "\n\n".join(context_parts)

        persona_instruction = (
            "You are a senior software engineer. Give precise, technical answers. "
            "Reference specific files, functions, and code patterns."
            if persona == "sde" else
            "You are a product manager. Explain in clear business language. "
            "Avoid code details. Focus on features, user value, and business impact."
        )

        llm = get_llm(temperature=0.2)
        prompt = f"""You are an AI assistant helping users understand a software codebase.

{persona_instruction}

## Generated Documentation (primary reference — use this first)
{doc_context or 'Documentation not yet generated — rely on code sections below.'}

## Project Summary
{project_summary}

## Relevant Code Sections
{code_context or 'No specific code sections matched this question.'}

## User Question
{question}

Answer clearly and specifically. Ground your answer in the documentation and code above."""

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return {
            "answer": response.content,
            "sources": sources[:5],
            "question": question
        }

    except Exception as e:
        return {
            "answer": f"Could not generate answer: {str(e)[:200]}. Ensure analysis is complete and OPENAI_API_KEY is set in .env.",
            "sources": [],
            "question": question
        }
