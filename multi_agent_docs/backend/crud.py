from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional, Dict, Any
from backend.database import User, Project, AnalysisLog, Document, Diagram, QAEntry, AgentTrace, gen_id
from backend.auth import get_password_hash

# Users
def create_user(db: Session, email: str, username: str, password: str, role: str = "user") -> User:
    user = User(
        id=gen_id(),
        email=email,
        username=username,
        password_hash=get_password_hash(password),
        role=role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()

def get_all_users(db: Session) -> List[User]:
    return db.query(User).all()

def update_user(db: Session, user_id: str, **kwargs) -> Optional[User]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    for k, v in kwargs.items():
        setattr(user, k, v)
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user

def delete_user(db: Session, user_id: str) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True

# Projects
def create_project(db: Session, user_id: str, name: str, description: str,
                   personas: list, analysis_config: dict) -> Project:
    project = Project(
        id=gen_id(),
        user_id=user_id,
        name=name,
        description=description,
        personas=personas,
        analysis_config=analysis_config,
        status="created"
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

def get_project(db: Session, project_id: str) -> Optional[Project]:
    return db.query(Project).filter(Project.id == project_id).first()

def get_user_projects(db: Session, user_id: str) -> List[Project]:
    return db.query(Project).filter(Project.user_id == user_id).order_by(Project.created_at.desc()).all()

def get_all_projects(db: Session) -> List[Project]:
    return db.query(Project).order_by(Project.created_at.desc()).all()

def update_project(db: Session, project_id: str, **kwargs) -> Optional[Project]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None
    for k, v in kwargs.items():
        setattr(project, k, v)
    project.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(project)
    return project

def delete_project(db: Session, project_id: str) -> bool:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return False
    db.delete(project)
    db.commit()
    return True

# Logs
def add_log(db: Session, project_id: str, message: str,
            level: str = "info", agent: str = "system") -> AnalysisLog:
    log = AnalysisLog(
        id=gen_id(),
        project_id=project_id,
        level=level,
        message=message,
        agent=agent
    )
    db.add(log)
    db.commit()
    return log

def get_project_logs(db: Session, project_id: str, limit: int = 200) -> List[AnalysisLog]:
    return (db.query(AnalysisLog)
            .filter(AnalysisLog.project_id == project_id)
            .order_by(AnalysisLog.timestamp.asc())
            .limit(limit).all())

def get_recent_logs(db: Session, project_id: str, since_id: Optional[str] = None) -> List[AnalysisLog]:
    q = db.query(AnalysisLog).filter(AnalysisLog.project_id == project_id)
    if since_id:
        q = q.filter(AnalysisLog.id > since_id)
    return q.order_by(AnalysisLog.timestamp.asc()).limit(100).all()

# Documents
def upsert_document(db: Session, project_id: str, persona: str, title: str, content: str) -> Document:
    doc = db.query(Document).filter(
        Document.project_id == project_id,
        Document.persona == persona
    ).first()
    if doc:
        doc.title = title
        doc.content = content
        doc.updated_at = datetime.utcnow()
    else:
        doc = Document(
            id=gen_id(),
            project_id=project_id,
            persona=persona,
            title=title,
            content=content
        )
        db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc

def get_project_documents(db: Session, project_id: str) -> List[Document]:
    return db.query(Document).filter(Document.project_id == project_id).all()

def get_document_by_persona(db: Session, project_id: str, persona: str) -> Optional[Document]:
    return db.query(Document).filter(
        Document.project_id == project_id,
        Document.persona == persona
    ).first()

# Diagrams
def save_diagram(db: Session, project_id: str, diagram_type: str, title: str,
                 description: str, mermaid_code: str, persona: str = "both") -> Diagram:
    # Delete existing diagram of same type for this project
    db.query(Diagram).filter(
        Diagram.project_id == project_id,
        Diagram.diagram_type == diagram_type
    ).delete()
    diagram = Diagram(
        id=gen_id(),
        project_id=project_id,
        diagram_type=diagram_type,
        title=title,
        description=description,
        mermaid_code=mermaid_code,
        persona=persona
    )
    db.add(diagram)
    db.commit()
    db.refresh(diagram)
    return diagram

def get_project_diagrams(db: Session, project_id: str) -> List[Diagram]:
    return db.query(Diagram).filter(Diagram.project_id == project_id).all()

# Q&A
def save_qa(db: Session, project_id: str, persona: str, question: str,
            answer: str, sources: list) -> QAEntry:
    entry = QAEntry(
        id=gen_id(),
        project_id=project_id,
        persona=persona,
        question=question,
        answer=answer,
        sources=sources
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry

def get_project_qa(db: Session, project_id: str) -> List[QAEntry]:
    return (db.query(QAEntry)
            .filter(QAEntry.project_id == project_id)
            .order_by(QAEntry.created_at.desc())
            .limit(50).all())

# Agent Traces
def save_trace(db: Session, project_id: str, agent_name: str, input_tokens: int,
               output_tokens: int, cost_usd: float, latency_ms: int,
               status: str = "success", error: str = "", metadata: dict = None) -> AgentTrace:
    trace = AgentTrace(
        id=gen_id(),
        project_id=project_id,
        agent_name=agent_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        status=status,
        error=error,
        trace_metadata=metadata or {}
    )
    db.add(trace)
    db.commit()
    return trace

def get_project_traces(db: Session, project_id: str) -> List[AgentTrace]:
    return (db.query(AgentTrace)
            .filter(AgentTrace.project_id == project_id)
            .order_by(AgentTrace.created_at.asc()).all())

# Admin stats
def get_admin_stats(db: Session) -> dict:
    from backend.database import Project as P
    return {
        "total_users": db.query(User).count(),
        "total_projects": db.query(P).count(),
        "active_analyses": db.query(P).filter(P.status.in_(["preprocessing", "analyzing"])).count(),
        "completed_analyses": db.query(P).filter(P.status == "completed").count(),
        "failed_analyses": db.query(P).filter(P.status == "failed").count(),
    }
