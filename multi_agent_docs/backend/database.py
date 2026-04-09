from sqlalchemy import (
    create_engine, Column, String, Integer, Text, DateTime,
    Boolean, ForeignKey, JSON, Float
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid
from backend.config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def gen_id():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="user")  # "user" or "admin"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")

class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="created")  # created, preprocessing, analyzing, paused, completed, failed
    personas = Column(JSON, default=list)  # ["sde", "pm"]
    repo_type = Column(String, default="")
    repo_source = Column(String, default="")  # "zip" or "github"
    github_url = Column(String, default="")
    zip_filename = Column(String, default="")
    upload_path = Column(String, default="")
    extracted_path = Column(String, default="")
    analysis_config = Column(JSON, default=dict)  # depth, verbosity, etc.
    progress = Column(Integer, default=0)
    current_agent = Column(String, default="")
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="projects")
    logs = relationship("AnalysisLog", back_populates="project", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    diagrams = relationship("Diagram", back_populates="project", cascade="all, delete-orphan")
    qa_history = relationship("QAEntry", back_populates="project", cascade="all, delete-orphan")

class AnalysisLog(Base):
    __tablename__ = "analysis_logs"

    id = Column(String, primary_key=True, default=gen_id)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    level = Column(String, default="info")  # info, warning, error, milestone
    message = Column(Text, nullable=False)
    agent = Column(String, default="system")
    timestamp = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="logs")

class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=gen_id)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    persona = Column(String, nullable=False)  # "sde" or "pm"
    title = Column(String, default="")
    content = Column(Text, default="")
    doc_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="documents")

class Diagram(Base):
    __tablename__ = "diagrams"

    id = Column(String, primary_key=True, default=gen_id)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    diagram_type = Column(String, nullable=False)  # architecture, sequence, er, flowchart, class
    title = Column(String, default="")
    description = Column(Text, default="")
    mermaid_code = Column(Text, default="")
    persona = Column(String, default="both")  # sde, pm, both
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="diagrams")

class QAEntry(Base):
    __tablename__ = "qa_entries"

    id = Column(String, primary_key=True, default=gen_id)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    persona = Column(String, default="sde")
    question = Column(Text, nullable=False)
    answer = Column(Text, default="")
    sources = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="qa_history")

class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id = Column(String, primary_key=True, default=gen_id)
    project_id = Column(String, nullable=False)
    agent_name = Column(String, nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    latency_ms = Column(Integer, default=0)
    status = Column(String, default="success")
    error = Column(Text, default="")
    trace_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

def create_tables():
    Base.metadata.create_all(bind=engine)

# Create tables on import
create_tables()
