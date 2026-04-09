from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime

# Auth
class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    role: str = "user"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("user", "admin"):
            raise ValueError("Role must be 'user' or 'admin'")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    email: str
    username: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

# Projects
class AnalysisConfig(BaseModel):
    depth: str = "standard"          # quick, standard, deep
    verbosity: str = "medium"        # low, medium, high
    generate_diagrams: bool = True
    web_search: bool = True
    focus_areas: List[str] = []

class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    personas: List[str] = ["sde", "pm"]
    github_url: str = ""
    analysis_config: AnalysisConfig = AnalysisConfig()

    @field_validator("personas")
    @classmethod
    def validate_personas(cls, v):
        valid = {"sde", "pm"}
        for p in v:
            if p not in valid:
                raise ValueError(f"Invalid persona: {p}. Must be 'sde' or 'pm'")
        return v

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    analysis_config: Optional[AnalysisConfig] = None

class ProjectOut(BaseModel):
    id: str
    user_id: str
    name: str
    description: str
    status: str
    personas: List[str]
    repo_type: str
    repo_source: str
    github_url: str
    progress: int
    current_agent: str
    error_message: str
    analysis_config: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Logs
class LogOut(BaseModel):
    id: str
    project_id: str
    level: str
    message: str
    agent: str
    timestamp: datetime

    class Config:
        from_attributes = True

# Documents
class DocumentOut(BaseModel):
    id: str
    project_id: str
    persona: str
    title: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True

# Diagrams
class DiagramOut(BaseModel):
    id: str
    project_id: str
    diagram_type: str
    title: str
    description: str
    mermaid_code: str
    persona: str
    created_at: datetime

    class Config:
        from_attributes = True

# Q&A
class QARequest(BaseModel):
    question: str
    persona: str = "sde"

class QAResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]] = []
    question: str

class QAEntryOut(BaseModel):
    id: str
    persona: str
    question: str
    answer: str
    sources: List[Any]
    created_at: datetime

    class Config:
        from_attributes = True

# Control
class ResumeRequest(BaseModel):
    context: str = ""

class UserContextRequest(BaseModel):
    context: str

# Analysis Summary
class AnalysisSummary(BaseModel):
    repo_type: str = ""
    entry_points: List[str] = []
    total_files: int = 0
    total_chunks: int = 0
    api_endpoints: int = 0
    detected_frameworks: List[str] = []
    key_features: List[str] = []

# Admin
class AdminStats(BaseModel):
    total_users: int
    total_projects: int
    active_analyses: int
    completed_analyses: int
    failed_analyses: int

class UserAdminUpdate(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = None

# Agent Trace
class AgentTraceOut(BaseModel):
    id: str
    project_id: str
    agent_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
