"""
Handles ZIP extraction and GitHub repository cloning.
"""
import os
import zipfile
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, Optional
from backend.config import (
    UPLOADS_DIR, MAX_FILE_SIZE_BYTES, SKIP_PATTERNS,
    BINARY_EXTENSIONS, CODE_EXTENSIONS
)

ALLOWED_CODE_EXTENSIONS = CODE_EXTENSIONS

def validate_zip(file_path: str) -> Tuple[bool, str]:
    """Validate a ZIP file before processing."""
    path = Path(file_path)

    if not path.exists():
        return False, "File not found"

    size = path.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        return False, f"File too large ({size // (1024*1024)}MB). Max: 100MB"

    if not zipfile.is_zipfile(file_path):
        return False, "File is not a valid ZIP archive (corrupted or wrong format)"

    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            names = zf.namelist()
            if not names:
                return False, "ZIP file is empty"

            # Check for code files
            code_found = False
            for name in names:
                ext = Path(name).suffix.lower()
                base = Path(name).name.lower()
                if ext in ALLOWED_CODE_EXTENSIONS or base in {"dockerfile", "makefile", "rakefile"}:
                    code_found = True
                    break

            if not code_found:
                return False, "No recognizable code files found in repository (binary-only or documentation-only)"

    except zipfile.BadZipFile as e:
        return False, f"Corrupted ZIP file: {str(e)}"
    except Exception as e:
        return False, f"Error reading ZIP: {str(e)}"

    return True, "OK"

def extract_zip(zip_path: str, project_id: str) -> Tuple[bool, str, str]:
    """Extract ZIP to project directory. Returns (success, message, extract_path)."""
    extract_dir = UPLOADS_DIR / project_id / "repo"
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Check for zip bomb (total uncompressed size)
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > MAX_FILE_SIZE_BYTES * 3:  # Allow 3x compression ratio
                return False, "ZIP file expands too large (possible zip bomb)", ""

            zf.extractall(extract_dir)

        # If there's a single top-level directory, use that as root
        entries = list(extract_dir.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            return True, "Extracted successfully", str(entries[0])

        return True, "Extracted successfully", str(extract_dir)

    except Exception as e:
        return False, f"Extraction failed: {str(e)}", ""

def validate_github_url(url: str) -> Tuple[bool, str]:
    """Validate GitHub or Gist URL format."""
    url = url.strip()
    if not url:
        return False, "URL cannot be empty"

    valid_prefixes = [
        "https://github.com/",
        "http://github.com/",
        "git@github.com:",
        "https://gist.github.com/",
        "http://gist.github.com/",
    ]
    is_valid = any(url.startswith(p) for p in valid_prefixes)

    if not is_valid:
        return False, "Not a valid GitHub URL. Must start with https://github.com/ or https://gist.github.com/"

    # Gist URLs: https://gist.github.com/<gist_id>[.git] — only one path segment needed
    if "gist.github.com" in url:
        clean = url.replace("https://gist.github.com/", "").replace("http://gist.github.com/", "")
        if clean.endswith(".git"):
            clean = clean[:-4]
        if not clean.strip("/"):
            return False, "Malformed Gist URL. Expected format: https://gist.github.com/<gist_id>"
        return True, "OK"

    # Regular GitHub URLs: owner/repo
    clean = url.replace("https://github.com/", "").replace("http://github.com/", "")
    if clean.endswith(".git"):
        clean = clean[:-4]
    parts = clean.strip("/").split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return False, "Malformed GitHub URL. Expected format: https://github.com/owner/repo"

    return True, "OK"

def clone_github_repo(url: str, project_id: str) -> Tuple[bool, str, str]:
    """Clone a GitHub repository. Returns (success, message, repo_path)."""
    clone_dir = UPLOADS_DIR / project_id / "repo"
    clone_dir.mkdir(parents=True, exist_ok=True)
    repo_path = str(clone_dir)

    try:
        # Clean URL
        if not url.endswith(".git"):
            url = url.rstrip("/") + ".git"

        result = subprocess.run(
            ["git", "clone", "--depth=1", "--single-branch", url, repo_path],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            stderr = result.stderr.lower()
            if "repository not found" in stderr or "not found" in stderr:
                return False, "Repository not found. Check the URL or make it public.", ""
            if "authentication" in stderr or "403" in stderr or "401" in stderr:
                return False, "Repository is private or access denied.", ""
            return False, f"Clone failed: {result.stderr[:200]}", ""

        # Verify code files exist
        code_found = False
        for root, dirs, files in os.walk(repo_path):
            # Skip hidden/ignored dirs
            dirs[:] = [d for d in dirs if d not in SKIP_PATTERNS and not d.startswith('.')]
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in ALLOWED_CODE_EXTENSIONS:
                    code_found = True
                    break
            if code_found:
                break

        if not code_found:
            return False, "Repository contains no recognizable code files", ""

        return True, "Repository cloned successfully", repo_path

    except subprocess.TimeoutExpired:
        return False, "Clone timed out (120s). Repository may be too large.", ""
    except FileNotFoundError:
        return False, "git is not installed on this system", ""
    except Exception as e:
        return False, f"Clone error: {str(e)}", ""

def get_file_tree(repo_path: str, max_depth: int = 5) -> dict:
    """Build a file tree dict from repository path."""
    tree = {}
    repo = Path(repo_path)

    def _walk(path: Path, depth: int) -> dict:
        if depth > max_depth:
            return {}
        result = {}
        try:
            entries = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
            for entry in entries:
                name = entry.name
                # Skip ignored patterns
                if name in SKIP_PATTERNS or name.startswith('.'):
                    continue
                if entry.is_dir():
                    subtree = _walk(entry, depth + 1)
                    if subtree or depth < 3:  # Keep empty dirs near root
                        result[name + "/"] = subtree
                elif entry.is_file():
                    ext = entry.suffix.lower()
                    size = entry.stat().st_size
                    if size < 1024 * 1024:  # Skip files > 1MB
                        result[name] = {"size": size, "ext": ext}
        except PermissionError:
            pass
        return result

    return _walk(repo, 0)

def get_important_files(repo_path: str) -> list:
    """Identify important files for analysis (entry points, configs, etc.)."""
    important = []
    repo = Path(repo_path)

    # Priority files
    priority_names = {
        "main.py", "app.py", "server.py", "api.py", "index.py",
        "index.js", "index.ts", "app.js", "app.ts", "server.js",
        "main.go", "main.rs", "main.rb", "main.java", "main.cs",
        "manage.py", "wsgi.py", "asgi.py",
        "requirements.txt", "package.json", "Cargo.toml", "go.mod",
        "pom.xml", "build.gradle", "setup.py", "pyproject.toml",
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".env.example", "config.py", "settings.py", "config.js",
        "README.md", "README.rst"
    }

    # Collect all code files, prioritized
    all_files = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_PATTERNS and not d.startswith('.')]
        for f in files:
            full_path = os.path.join(root, f)
            ext = Path(f).suffix.lower()
            size = os.path.getsize(full_path)
            if size > 500 * 1024:  # Skip files > 500KB
                continue
            if ext in BINARY_EXTENSIONS:
                continue
            rel_path = os.path.relpath(full_path, repo_path)
            is_priority = f in priority_names or f.lower() in {p.lower() for p in priority_names}
            all_files.append({
                "path": full_path,
                "rel_path": rel_path,
                "name": f,
                "ext": ext,
                "size": size,
                "priority": is_priority
            })

    # Sort: priority first, then by size (larger files often more important), then alphabetical
    all_files.sort(key=lambda x: (not x["priority"], -x["size"], x["rel_path"]))

    return all_files[:200]  # Max 200 files

def detect_repo_type(repo_path: str, important_files: list) -> Tuple[str, list, dict]:
    """
    Detect the repository type, entry points, and dependencies.
    Returns (repo_type, entry_points, dependencies)
    """
    file_names = {f["name"].lower() for f in important_files}
    file_exts = {f["ext"] for f in important_files}

    # Check for dependency/config files
    has_requirements = "requirements.txt" in file_names or "setup.py" in file_names or "pyproject.toml" in file_names
    has_package_json = "package.json" in file_names
    has_go_mod = "go.mod" in file_names
    has_cargo = "cargo.toml" in file_names
    has_pom = "pom.xml" in file_names

    frameworks = []
    dependencies = {}

    # Detect language & framework
    if has_requirements or ".py" in file_exts:
        # Python project
        req_file = next((f for f in important_files if f["name"] == "requirements.txt"), None)
        if req_file:
            try:
                content = Path(req_file["path"]).read_text(encoding="utf-8", errors="ignore").lower()
                if "fastapi" in content:
                    frameworks.append("FastAPI")
                if "django" in content:
                    frameworks.append("Django")
                if "flask" in content:
                    frameworks.append("Flask")
                if "sqlalchemy" in content:
                    frameworks.append("SQLAlchemy")
                if "pydantic" in content:
                    frameworks.append("Pydantic")
                if "langchain" in content:
                    frameworks.append("LangChain")
                if "openai" in content:
                    frameworks.append("OpenAI")
                dependencies["python"] = content[:500]
            except Exception:
                pass

        if frameworks:
            repo_type = f"Python ({', '.join(frameworks[:3])})"
        else:
            repo_type = "Python"

    elif has_package_json:
        pkg_file = next((f for f in important_files if f["name"] == "package.json"), None)
        if pkg_file:
            try:
                import json
                content = json.loads(Path(pkg_file["path"]).read_text(encoding="utf-8", errors="ignore"))
                deps = {**content.get("dependencies", {}), **content.get("devDependencies", {})}
                dep_names = set(deps.keys())
                if "next" in dep_names:
                    frameworks.append("Next.js")
                if "react" in dep_names:
                    frameworks.append("React")
                if "vue" in dep_names:
                    frameworks.append("Vue.js")
                if "express" in dep_names:
                    frameworks.append("Express")
                if "nestjs" in str(dep_names) or "@nestjs/core" in dep_names:
                    frameworks.append("NestJS")
                if "typescript" in dep_names or ".ts" in file_exts:
                    frameworks.append("TypeScript")
                dependencies["node"] = str(list(deps.keys())[:20])
            except Exception:
                pass
        repo_type = f"JavaScript/TypeScript ({', '.join(frameworks[:3])})" if frameworks else "JavaScript"

    elif has_go_mod:
        repo_type = "Go"
    elif has_cargo:
        repo_type = "Rust"
    elif has_pom:
        repo_type = "Java (Maven)"
    else:
        # Infer from extensions
        if ".py" in file_exts:
            repo_type = "Python"
        elif ".js" in file_exts or ".ts" in file_exts:
            repo_type = "JavaScript/TypeScript"
        elif ".go" in file_exts:
            repo_type = "Go"
        elif ".rs" in file_exts:
            repo_type = "Rust"
        elif ".java" in file_exts:
            repo_type = "Java"
        elif ".cs" in file_exts:
            repo_type = "C#"
        elif ".rb" in file_exts:
            repo_type = "Ruby"
        else:
            repo_type = "Mixed/Other"

    # Find entry points
    entry_points = []
    entry_names = ["main.py", "app.py", "server.py", "api.py", "index.js",
                   "index.ts", "app.js", "app.ts", "server.js", "main.go",
                   "main.rs", "manage.py"]
    for ep in entry_names:
        match = next((f for f in important_files if f["name"].lower() == ep.lower()), None)
        if match:
            entry_points.append(match["rel_path"])

    return repo_type, entry_points, dependencies
