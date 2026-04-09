import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = BASE_DIR / "uploads"
CHROMA_DIR = BASE_DIR / "chroma_db"

DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)
CHROMA_DIR.mkdir(exist_ok=True)

# JWT
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-super-secret-key-12345")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# LLM
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")

# Langfuse (optional)
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

# Database
DATABASE_URL = f"sqlite:///{DATA_DIR}/app.db"

# File limits
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Analysis settings
SKIP_PATTERNS = {
    "node_modules", ".git", "__pycache__", ".pytest_cache", "venv", "env",
    ".venv", "dist", "build", ".next", ".nuxt", "coverage", ".nyc_output",
    ".tox", "*.egg-info", ".mypy_cache", ".ruff_cache", "htmlcov"
}
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".tar", ".gz",
    ".exe", ".dll", ".so", ".dylib", ".whl", ".pyc", ".pyo",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".ttf", ".woff", ".woff2"
}
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb",
    ".php", ".cpp", ".c", ".h", ".cs", ".swift", ".kt", ".scala",
    ".html", ".css", ".scss", ".less", ".vue", ".svelte",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env.example",
    ".sh", ".bash", ".zsh", ".sql", ".graphql", ".proto", ".xml",
    ".md", ".rst", ".txt", ".dockerfile", "Dockerfile", ".makefile"
}

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8501")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
