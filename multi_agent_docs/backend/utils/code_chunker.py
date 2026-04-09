"""
Chunks code files into logical units (functions, classes, modules).
Supports Python, JavaScript/TypeScript, Go, Java, etc.
"""
import re
from pathlib import Path
from typing import List, Dict, Any

def chunk_python_file(content: str, file_path: str) -> List[Dict[str, Any]]:
    """Extract functions and classes from Python code."""
    chunks = []
    lines = content.split("\n")
    n = len(lines)

    # Simple regex-based extraction
    func_pattern = re.compile(r'^(\s*)(async\s+)?def\s+(\w+)\s*\(', re.MULTILINE)
    class_pattern = re.compile(r'^class\s+(\w+)', re.MULTILINE)

    # Find all class definitions
    for m in class_pattern.finditer(content):
        start_line = content[:m.start()].count("\n")
        # Find end of class (next class or end of file)
        end_line = start_line + 50  # Default 50 lines
        class_lines = []
        indent = ""
        in_class = False
        for i, line in enumerate(lines[start_line:start_line + 100], start_line):
            if i == start_line:
                in_class = True
                class_lines.append(line)
            elif in_class and (line.startswith("class ") or line.startswith("def ")) and not line.startswith(" "):
                break
            else:
                class_lines.append(line)
        chunk_text = "\n".join(class_lines[:80])
        if len(chunk_text.strip()) > 20:
            chunks.append({
                "type": "class",
                "name": m.group(1),
                "content": chunk_text,
                "file_path": file_path,
                "start_line": start_line + 1,
                "end_line": start_line + len(class_lines),
                "language": "python"
            })

    # Find all function definitions
    for m in func_pattern.finditer(content):
        start_line = content[:m.start()].count("\n")
        func_name = m.group(3)
        indent = m.group(1)
        func_lines = []
        for i, line in enumerate(lines[start_line:start_line + 80], start_line):
            if i == start_line:
                func_lines.append(line)
            elif line.startswith(indent + "def ") or line.startswith(indent + "class ") or line.startswith(indent + "async def "):
                if i != start_line:
                    break
            elif indent and line and not line.startswith(indent) and not line.strip() == "":
                break
            else:
                func_lines.append(line)
        chunk_text = "\n".join(func_lines[:60])
        if len(chunk_text.strip()) > 20:
            chunks.append({
                "type": "function",
                "name": func_name,
                "content": chunk_text,
                "file_path": file_path,
                "start_line": start_line + 1,
                "end_line": start_line + len(func_lines),
                "language": "python"
            })

    # If no chunks found, add the whole file as one chunk
    if not chunks:
        chunks.append({
            "type": "module",
            "name": Path(file_path).stem,
            "content": content[:3000],
            "file_path": file_path,
            "start_line": 1,
            "end_line": len(lines),
            "language": "python"
        })

    return chunks

def chunk_js_file(content: str, file_path: str) -> List[Dict[str, Any]]:
    """Extract functions and classes from JS/TS code."""
    chunks = []
    lines = content.split("\n")

    # Patterns for JS/TS
    patterns = [
        (re.compile(r'^(export\s+)?(default\s+)?class\s+(\w+)', re.MULTILINE), "class"),
        (re.compile(r'^(export\s+)?(async\s+)?function\s+(\w+)', re.MULTILINE), "function"),
        (re.compile(r'^(export\s+)?const\s+(\w+)\s*=\s*(async\s+)?\(', re.MULTILINE), "arrow_function"),
        (re.compile(r'^(export\s+)?const\s+(\w+)\s*=\s*(async\s+)?function', re.MULTILINE), "function"),
    ]

    for pattern, chunk_type in patterns:
        for m in pattern.finditer(content):
            start_line = content[:m.start()].count("\n")
            # Get name from the right group
            name_groups = m.groups()
            name = name_groups[-1] if name_groups else "anonymous"
            if name in {"async", "default", "export", "const", "function", None}:
                # Try to get actual name
                rest = content[m.start():]
                name_match = re.search(r'\b(\w+)\b', rest.split("(")[0].split("=")[0])
                name = name_match.group(1) if name_match else "anonymous"

            chunk_lines = lines[start_line:start_line + 60]
            chunk_text = "\n".join(chunk_lines)
            if len(chunk_text.strip()) > 20:
                chunks.append({
                    "type": chunk_type,
                    "name": name,
                    "content": chunk_text,
                    "file_path": file_path,
                    "start_line": start_line + 1,
                    "end_line": start_line + 60,
                    "language": "javascript"
                })

    if not chunks:
        chunks.append({
            "type": "module",
            "name": Path(file_path).stem,
            "content": content[:3000],
            "file_path": file_path,
            "start_line": 1,
            "end_line": len(lines),
            "language": "javascript"
        })

    return chunks

def chunk_generic_file(content: str, file_path: str, language: str = "unknown") -> List[Dict[str, Any]]:
    """Generic chunker for other languages - splits by logical blocks."""
    lines = content.split("\n")
    chunks = []
    chunk_size = 60
    overlap = 10

    if len(lines) <= chunk_size:
        return [{
            "type": "module",
            "name": Path(file_path).stem,
            "content": content[:4000],
            "file_path": file_path,
            "start_line": 1,
            "end_line": len(lines),
            "language": language
        }]

    for i in range(0, len(lines), chunk_size - overlap):
        chunk_lines = lines[i:i + chunk_size]
        chunk_text = "\n".join(chunk_lines)
        if chunk_text.strip():
            chunks.append({
                "type": "block",
                "name": f"{Path(file_path).stem}_block_{i // chunk_size}",
                "content": chunk_text,
                "file_path": file_path,
                "start_line": i + 1,
                "end_line": i + len(chunk_lines),
                "language": language
            })

    return chunks

def chunk_file(file_path: str, content: str) -> List[Dict[str, Any]]:
    """Route to appropriate chunker based on file extension."""
    ext = Path(file_path).suffix.lower()

    if ext == ".py":
        return chunk_python_file(content, file_path)
    elif ext in {".js", ".ts", ".jsx", ".tsx", ".vue"}:
        return chunk_js_file(content, file_path)
    elif ext in {".java", ".kt", ".scala"}:
        return chunk_generic_file(content, file_path, "java")
    elif ext in {".go"}:
        return chunk_generic_file(content, file_path, "go")
    elif ext in {".rs"}:
        return chunk_generic_file(content, file_path, "rust")
    elif ext in {".rb"}:
        return chunk_generic_file(content, file_path, "ruby")
    elif ext in {".cs"}:
        return chunk_generic_file(content, file_path, "csharp")
    elif ext in {".json", ".yaml", ".yml", ".toml"}:
        return [{
            "type": "config",
            "name": Path(file_path).stem,
            "content": content[:2000],
            "file_path": file_path,
            "start_line": 1,
            "end_line": len(content.split("\n")),
            "language": ext.lstrip(".")
        }]
    elif ext in {".md", ".rst"}:
        return [{
            "type": "documentation",
            "name": Path(file_path).stem,
            "content": content[:3000],
            "file_path": file_path,
            "start_line": 1,
            "end_line": len(content.split("\n")),
            "language": "markdown"
        }]
    else:
        return chunk_generic_file(content, file_path)

def extract_api_info(content: str, file_path: str, language: str = "python") -> List[Dict[str, Any]]:
    """Extract API endpoint information from code."""
    endpoints = []
    ext = Path(file_path).suffix.lower()

    if ext == ".py":
        # FastAPI/Flask patterns
        patterns = [
            # FastAPI
            re.compile(r'@\w+\.(get|post|put|delete|patch|options)\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE),
            # Flask
            re.compile(r'@\w+\.route\s*\(\s*["\']([^"\']+)["\'].*?(methods\s*=\s*\[([^\]]+)\])?', re.IGNORECASE),
        ]
        for line_no, line in enumerate(content.split("\n"), 1):
            for p in patterns:
                m = p.search(line)
                if m:
                    groups = m.groups()
                    method = groups[0].upper() if groups[0] else "GET"
                    path = groups[1] if len(groups) > 1 and groups[1] else groups[0]
                    endpoints.append({
                        "method": method,
                        "path": path,
                        "file": file_path,
                        "line": line_no
                    })

    elif ext in {".js", ".ts"}:
        # Express.js patterns
        pattern = re.compile(r'\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE)
        for line_no, line in enumerate(content.split("\n"), 1):
            m = pattern.search(line)
            if m:
                endpoints.append({
                    "method": m.group(1).upper(),
                    "path": m.group(2),
                    "file": file_path,
                    "line": line_no
                })

    return endpoints

def extract_db_models(content: str, file_path: str) -> List[Dict[str, Any]]:
    """Extract database model definitions."""
    models = []
    ext = Path(file_path).suffix.lower()

    if ext == ".py":
        # SQLAlchemy models
        class_pattern = re.compile(r'^class\s+(\w+)\s*\([^)]*(?:Base|Model|db\.Model)[^)]*\)', re.MULTILINE)
        for m in class_pattern.finditer(content):
            start = content[:m.start()].count("\n")
            # Get fields
            lines = content.split("\n")
            fields = []
            for line in lines[start:start + 40]:
                col_match = re.search(r'(\w+)\s*=\s*(?:Column|mapped_column)\s*\(([^)]+)\)', line)
                if col_match:
                    fields.append({"name": col_match.group(1), "definition": col_match.group(2)[:50]})
            models.append({
                "name": m.group(1),
                "file": file_path,
                "line": start + 1,
                "fields": fields[:20]
            })

    return models
