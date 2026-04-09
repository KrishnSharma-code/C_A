"""
Handles ZIP extraction and GitHub repository cloning.
"""
import os
import re
import zipfile
import subprocess
from pathlib import Path
from typing import Tuple, Optional
from backend.config import (
    UPLOADS_DIR, MAX_FILE_SIZE_BYTES, SKIP_PATTERNS,
    BINARY_EXTENSIONS, CODE_EXTENSIONS
)


ALLOWED_CODE_EXTENSIONS = CODE_EXTENSIONS


# ---------------------------------------------------------------------------
# ZIP helpers
# ---------------------------------------------------------------------------

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

            code_found = any(
                Path(name).suffix.lower() in ALLOWED_CODE_EXTENSIONS
                or Path(name).name.lower() in {"dockerfile", "makefile", "rakefile"}
                for name in names
            )
            if not code_found:
                return False, "No recognizable code files found in ZIP"

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
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > MAX_FILE_SIZE_BYTES * 3:
                return False, "ZIP expands too large", ""
            zf.extractall(extract_dir)

        entries = list(extract_dir.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            return True, "Extracted successfully", str(entries[0])

        return True, "Extracted successfully", str(extract_dir)

    except Exception as e:
        return False, f"Extraction failed: {str(e)}", ""


# ---------------------------------------------------------------------------
# GitHub URL helpers
# ---------------------------------------------------------------------------

def _normalize_github_url(url: str) -> Tuple[str, Optional[str]]:
    """
    Convert any supported GitHub URL variant to a bare owner/repo clone URL
    and an optional branch name.

    Supported input forms:
      https://github.com/owner/repo
      https://github.com/owner/repo.git
      https://github.com/owner/repo/blob/branch/path/to/file.py
      https://github.com/owner/repo/tree/branch/optional/subpath
      https://gist.github.com/<gist_id>
      https://gist.github.com/<gist_id>.git

    Returns:
      (clone_url, branch)   — branch is None when not specified in the URL
    """
    url = url.strip().split('?')[0].rstrip('/')

    # blob or tree URLs  →  extract owner/repo + branch
    m = re.match(
        r'(https?://github\.com/[^/]+/[^/]+)/(blob|tree)/([^/]+)',
        url
    )
    if m:
        base = m.group(1)       # https://github.com/owner/repo
        branch = m.group(3)     # branch name
        return base.rstrip('.git') , branch

    # Plain repo URL (with or without .git)
    return url.rstrip('.git').rstrip('/'), None


def validate_github_url(url: str) -> Tuple[bool, str]:
    """
    Validate a GitHub or Gist URL.

    Accepted patterns:
      - https://github.com/owner/repo
      - https://github.com/owner/repo/blob/branch/path/to/file
      - https://github.com/owner/repo/tree/branch
      - https://gist.github.com/<gist_id>
      (all with or without .git suffix, with or without query strings)

    Rejected with a descriptive message:
      - GitHub topic pages  (github.com/topics/...)
      - GitHub search pages (github.com/search?...)
      - Non-GitHub URLs
    """
    raw = url.strip().split('?')[0]   # ignore query strings for pattern matching

    if not raw:
        return False, "URL cannot be empty"

    # Reject topic / search pages — they are not repositories
    if re.search(r'github\.com/topics/', raw):
        return False, (
            "That is a GitHub topic page, not a repository. "
            "Find a repository on that page and paste its URL, "
            "e.g. https://github.com/owner/repo"
        )
    if re.search(r'github\.com/search', raw):
        return False, (
            "GitHub search pages cannot be cloned. "
            "Paste a direct repository URL instead."
        )

    # Must start with a recognised prefix
    valid_prefixes = [
        "https://github.com/",
        "http://github.com/",
        "git@github.com:",
        "https://gist.github.com/",
        "http://gist.github.com/",
    ]
    if not any(raw.startswith(p) for p in valid_prefixes):
        return False, (
            "Not a valid GitHub URL. "
            "Must start with https://github.com/ or https://gist.github.com/"
        )

    # Gist: single path segment is enough
    if "gist.github.com" in raw:
        gist_id = (
            raw.replace("https://gist.github.com/", "")
               .replace("http://gist.github.com/", "")
               .rstrip(".git")
               .strip("/")
        )
        if not gist_id:
            return False, "Malformed Gist URL. Expected: https://gist.github.com/<gist_id>"
        return True, "OK"

    # blob / tree URLs — validate that owner/repo are present before the keyword
    if re.search(r'/(blob|tree)/', raw):
        m = re.match(r'https?://github\.com/([^/]+)/([^/]+)/(blob|tree)/', raw)
        if not m:
            return False, "Malformed GitHub blob/tree URL"
        return True, "OK"

    # Plain owner/repo URL
    clean = (
        raw.replace("https://github.com/", "")
           .replace("http://github.com/", "")
           .rstrip(".git")
           .strip("/")
    )
    parts = clean.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return False, "Malformed GitHub URL. Expected: https://github.com/owner/repo"

    return True, "OK"


def clone_github_repo(url: str, project_id: str) -> Tuple[bool, str, str]:
    """
    Clone a GitHub repository (or Gist) to a local directory.

    Handles all URL forms accepted by validate_github_url, including
    blob/tree URLs (the branch is extracted automatically).

    Returns (success, message, repo_path).
    """
    clone_dir = UPLOADS_DIR / project_id / "repo"
    clone_dir.mkdir(parents=True, exist_ok=True)
    repo_path = str(clone_dir)

    try:
        # Normalise URL and extract optional branch
        clean_url, branch = _normalize_github_url(url)

        if not clean_url.endswith(".git"):
            clean_url = clean_url + ".git"

        git_cmd = ["git", "clone", "--depth=1"]
        if branch:
            git_cmd += ["--branch", branch]
        git_cmd += [clean_url, repo_path]

        result = subprocess.run(
            git_cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            stderr = result.stderr.lower()
            if "repository not found" in stderr or "not found" in stderr:
                return False, "Repository not found. Check the URL and make sure it is public.", ""
            if "authentication" in stderr or "403" in stderr or "401" in stderr:
                return False, "Repository is private or access denied.", ""
            if "invalid branch" in stderr or "remote branch" in stderr:
                # Branch specified in URL does not exist — retry without branch
                git_cmd_retry = [
                    "git", "clone", "--depth=1", clean_url, repo_path
                ]
                result2 = subprocess.run(
                    git_cmd_retry, capture_output=True, text=True, timeout=120
                )
                if result2.returncode != 0:
                    return False, f"Clone failed: {result2.stderr[:200]}", ""
            else:
                return False, f"Clone failed: {result.stderr[:200]}", ""

        # Verify at least one code file exists
        code_found = False
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_PATTERNS and not d.startswith('.')]
            for f in files:
                if Path(f).suffix.lower() in ALLOWED_CODE_EXTENSIONS:
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


# ---------------------------------------------------------------------------
# File tree / discovery helpers (unchanged)
# ---------------------------------------------------------------------------

def get_file_tree(repo_path: str, max_depth: int = 5) -> dict:
    """Build a file tree dict from repository path."""
    repo = Path(repo_path)

    def _walk(path: Path, depth: int) -> dict:
        if depth > max_depth:
            return {}
        result = {}
        try:
            entries = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
            for entry in entries:
                name = entry.name
                if name in SKIP_PATTERNS or name.startswith('.'):
                    continue
                if entry.is_dir():
                    subtree = _walk(entry, depth + 1)
                    if subtree or depth < 3:
                        result[name + "/"] = subtree
                elif entry.is_file():
                    ext = entry.suffix.lower()
                    size = entry.stat().st_size
                    if size < 1024 * 1024:
                        result[name] = {"size": size, "ext": ext}
        except PermissionError:
            pass
        return result

    return _walk(repo, 0)


def get_important_files(repo_path: str) -> list:
    """Identify important files for analysis (entry points, configs, etc.)."""
    repo = Path(repo_path)

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

    all_files = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_PATTERNS and not d.startswith('.')]
        for f in files:
            full_path = os.path.join(root, f)
            ext = Path(f).suffix.lower()
            size = os.path.getsize(full_path)
            if size > 500 * 1024 or ext in BINARY_EXTENSIONS:
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

    all_files.sort(key=lambda x: (not x["priority"], -x["size"], x["rel_path"]))
    return all_files[:200]


def detect_repo_type(repo_path: str, important_files: list) -> Tuple[str, list, dict]:
    """
    Detect repository type, entry points, and dependencies.
    Returns (repo_type, entry_points, dependencies).
    """
    file_names = {f["name"].lower() for f in important_files}
    file_exts = {f["ext"] for f in important_files}

    has_requirements = any(n in file_names for n in ("requirements.txt", "setup.py", "pyproject.toml"))
    has_package_json = "package.json" in file_names
    has_go_mod = "go.mod" in file_names
    has_cargo = "cargo.toml" in file_names
    has_pom = "pom.xml" in file_names

    frameworks = []
    dependencies = {}

    if has_requirements or ".py" in file_exts:
        req_file = next((f for f in important_files if f["name"] == "requirements.txt"), None)
        if req_file:
            try:
                content = Path(req_file["path"]).read_text(encoding="utf-8", errors="ignore").lower()
                for fw in ("fastapi", "django", "flask", "sqlalchemy", "pydantic", "langchain", "openai"):
                    if fw in content:
                        frameworks.append(fw.capitalize() if fw != "openai" else "OpenAI")
                dependencies["python"] = content[:500]
            except Exception:
                pass
        repo_type = f"Python ({', '.join(frameworks[:3])})" if frameworks else "Python"

    elif has_package_json:
        pkg_file = next((f for f in important_files if f["name"] == "package.json"), None)
        if pkg_file:
            try:
                import json
                pkg = json.loads(Path(pkg_file["path"]).read_text(encoding="utf-8", errors="ignore"))
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                dep_names = set(deps.keys())
                for fw, label in (("next", "Next.js"), ("react", "React"), ("vue", "Vue.js"),
                                  ("express", "Express"), ("typescript", "TypeScript")):
                    if fw in dep_names:
                        frameworks.append(label)
                if "@nestjs/core" in dep_names:
                    frameworks.append("NestJS")
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
        ext_map = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
                   ".go": "Go", ".rs": "Rust", ".java": "Java",
                   ".cs": "C#", ".rb": "Ruby"}
        repo_type = next((label for ext, label in ext_map.items() if ext in file_exts), "Mixed/Other")

    entry_names = ["main.py", "app.py", "server.py", "api.py", "index.js",
                   "index.ts", "app.js", "app.ts", "server.js", "main.go",
                   "main.rs", "manage.py"]
    entry_points = [
        f["rel_path"] for ep in entry_names
        for f in important_files if f["name"].lower() == ep.lower()
    ]

    return repo_type, entry_points, dependencies
