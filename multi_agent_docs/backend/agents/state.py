from typing import TypedDict, List, Dict, Any, Optional, Annotated
import operator

class AnalysisState(TypedDict):
    # Project info
    project_id: str
    repo_path: str
    personas: List[str]
    analysis_depth: str       # quick, standard, deep
    verbosity: str            # low, medium, high
    generate_diagrams: bool
    web_search_enabled: bool
    focus_areas: List[str]

    # Repository structure
    repo_type: str
    entry_points: List[str]
    config_files: List[str]
    dependencies: Dict[str, Any]
    file_tree: Dict[str, Any]
    important_files: List[Dict[str, Any]]
    total_files: int

    # Code analysis results
    all_chunks: List[Dict[str, Any]]
    total_chunks: int
    api_endpoints: List[Dict[str, Any]]
    db_models: List[Dict[str, Any]]
    auth_patterns: List[str]
    business_logic: List[str]
    key_features: List[str]
    tech_stack: List[str]

    # Web search results
    web_findings: Dict[str, str]

    # Generated documentation
    sde_report: str
    pm_report: str

    # Diagrams (type -> mermaid code)
    diagrams: Dict[str, Dict[str, str]]

    # Control state
    is_paused: bool
    pause_requested: bool
    current_agent: str
    progress: int
    messages: Annotated[List[str], operator.add]
    user_context: List[str]
    errors: Annotated[List[str], operator.add]

    # Langfuse tracing
    trace_data: List[Dict[str, Any]]
