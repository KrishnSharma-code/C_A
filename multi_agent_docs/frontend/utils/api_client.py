"""
HTTP API client for communicating with the FastAPI backend.
"""
import requests
import json
from typing import Optional, Dict, Any, List
import streamlit as st

BACKEND_URL = "http://localhost:8000"


def _headers(token: Optional[str] = None) -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    tok = token or st.session_state.get("token", "")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def handle_response(resp: requests.Response) -> Optional[Dict]:
    """Handle API response, show errors in Streamlit if needed."""
    if resp.status_code == 200 or resp.status_code == 201:
        try:
            return resp.json()
        except Exception:
            return {}
    else:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        return {"error": detail, "status_code": resp.status_code}


def signup(email: str, username: str, password: str, role: str = "user") -> Dict:
    resp = requests.post(
        f"{BACKEND_URL}/api/auth/signup",
        json={"email": email, "username": username, "password": password, "role": role},
        timeout=10
    )
    return handle_response(resp)


def login(email: str, password: str) -> Dict:
    resp = requests.post(
        f"{BACKEND_URL}/api/auth/login-json",
        json={"email": email, "password": password},
        timeout=10
    )
    return handle_response(resp)


def get_me(token: str) -> Dict:
    resp = requests.get(
        f"{BACKEND_URL}/api/auth/me",
        headers=_headers(token),
        timeout=5
    )
    return handle_response(resp)


def list_projects() -> List[Dict]:
    resp = requests.get(
        f"{BACKEND_URL}/api/projects",
        headers=_headers(),
        timeout=10
    )
    result = handle_response(resp)
    if isinstance(result, list):
        return result
    return []


def create_project_with_upload(
    name: str,
    description: str,
    personas: List[str],
    analysis_config: Dict,
    zip_file=None,
    github_url: str = ""
) -> Dict:
    """Create project with ZIP or GitHub URL."""
    import json as json_lib

    token = st.session_state.get("token", "")
    headers = {"Authorization": f"Bearer {token}"}

    data = {
        "name": name,
        "description": description,
        "personas": json_lib.dumps(personas),
        "analysis_config": json_lib.dumps(analysis_config),
        "github_url": github_url
    }

    files = {}
    if zip_file is not None:
        files["zip_file"] = (zip_file.name, zip_file.getvalue(), "application/zip")

    try:
        if files:
            resp = requests.post(
                f"{BACKEND_URL}/api/projects/upload",
                data=data,
                files=files,
                headers=headers,
                timeout=60
            )
        else:
            resp = requests.post(
                f"{BACKEND_URL}/api/projects/upload",
                data=data,
                headers=headers,
                timeout=30
            )
        return handle_response(resp)
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot connect to backend. Is it running?"}
    except Exception as e:
        return {"error": str(e)}


def get_project(project_id: str) -> Dict:
    try:
        resp = requests.get(
            f"{BACKEND_URL}/api/projects/{project_id}",
            headers=_headers(),
            timeout=30
        )
        return handle_response(resp)
    except requests.exceptions.Timeout:
        return {"error": "Request timed out — backend may be busy with analysis. Retrying..."}
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot connect to backend. Is it running?"}


def delete_project(project_id: str) -> Dict:
    resp = requests.delete(
        f"{BACKEND_URL}/api/projects/{project_id}",
        headers=_headers(),
        timeout=10
    )
    return handle_response(resp)


def start_analysis(project_id: str) -> Dict:
    resp = requests.post(
        f"{BACKEND_URL}/api/projects/{project_id}/start",
        headers=_headers(),
        timeout=10
    )
    return handle_response(resp)


def pause_analysis(project_id: str) -> Dict:
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/projects/{project_id}/pause",
            headers=_headers(),
            timeout=15
        )
        return handle_response(resp)
    except Exception as e:
        return {"error": str(e)}


def resume_analysis(project_id: str, context: str = "") -> Dict:
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/projects/{project_id}/resume",
            headers=_headers(),
            json={"context": context},
            timeout=15
        )
        return handle_response(resp)
    except Exception as e:
        return {"error": str(e)}


def add_context(project_id: str, context: str) -> Dict:
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/projects/{project_id}/context",
            headers=_headers(),
            json={"context": context},
            timeout=15
        )
        return handle_response(resp)
    except Exception as e:
        return {"error": str(e)}


def get_logs(project_id: str, limit: int = 200) -> List[Dict]:
    try:
        resp = requests.get(
            f"{BACKEND_URL}/api/projects/{project_id}/logs?limit={limit}",
            headers=_headers(),
            timeout=20
        )
        result = handle_response(resp)
        if isinstance(result, list):
            return result
        return []
    except Exception:
        return []


def get_documents(project_id: str) -> List[Dict]:
    resp = requests.get(
        f"{BACKEND_URL}/api/projects/{project_id}/documents",
        headers=_headers(),
        timeout=10
    )
    result = handle_response(resp)
    if isinstance(result, list):
        return result
    return []


def get_document_by_persona(project_id: str, persona: str) -> Optional[Dict]:
    resp = requests.get(
        f"{BACKEND_URL}/api/projects/{project_id}/documents/{persona}",
        headers=_headers(),
        timeout=10
    )
    result = handle_response(resp)
    if "error" in result:
        return None
    return result


def get_diagrams(project_id: str) -> List[Dict]:
    resp = requests.get(
        f"{BACKEND_URL}/api/projects/{project_id}/diagrams",
        headers=_headers(),
        timeout=10
    )
    result = handle_response(resp)
    if isinstance(result, list):
        return result
    return []


def ask_question(project_id: str, question: str, persona: str = "sde", auth_token: str = None) -> Dict:
    try:
        h = {"Authorization": f"Bearer {auth_token}"} if auth_token else _headers()
        resp = requests.post(
            f"{BACKEND_URL}/api/projects/{project_id}/qa",
            headers=h,
            json={"question": question, "persona": persona},
            timeout=60
        )
        return handle_response(resp)
    except requests.exceptions.Timeout:
        return {"error": "Request timed out. The AI is taking longer than expected."}
    except Exception as e:
        return {"error": str(e)}


def get_qa_history(project_id: str) -> List[Dict]:
    resp = requests.get(
        f"{BACKEND_URL}/api/projects/{project_id}/qa/history",
        headers=_headers(),
        timeout=5
    )
    result = handle_response(resp)
    if isinstance(result, list):
        return result
    return []


def search_code(project_id: str, query: str, n: int = 5) -> Dict:
    resp = requests.get(
        f"{BACKEND_URL}/api/projects/{project_id}/search?q={query}&n={n}",
        headers=_headers(),
        timeout=10
    )
    return handle_response(resp)


def get_traces(project_id: str) -> List[Dict]:
    try:
        resp = requests.get(
            f"{BACKEND_URL}/api/projects/{project_id}/traces",
            headers=_headers(),
            timeout=20
        )
        result = handle_response(resp)
        if isinstance(result, list):
            return result
        return []
    except Exception:
        return []


def admin_get_stats() -> Dict:
    resp = requests.get(
        f"{BACKEND_URL}/api/admin/stats",
        headers=_headers(),
        timeout=5
    )
    return handle_response(resp)


def admin_list_users() -> List[Dict]:
    resp = requests.get(
        f"{BACKEND_URL}/api/admin/users",
        headers=_headers(),
        timeout=5
    )
    result = handle_response(resp)
    if isinstance(result, list):
        return result
    return []


def admin_update_user(user_id: str, updates: Dict) -> Dict:
    resp = requests.put(
        f"{BACKEND_URL}/api/admin/users/{user_id}",
        headers=_headers(),
        json=updates,
        timeout=5
    )
    return handle_response(resp)


def admin_delete_user(user_id: str) -> Dict:
    resp = requests.delete(
        f"{BACKEND_URL}/api/admin/users/{user_id}",
        headers=_headers(),
        timeout=5
    )
    return handle_response(resp)


def admin_list_projects() -> List[Dict]:
    resp = requests.get(
        f"{BACKEND_URL}/api/admin/projects",
        headers=_headers(),
        timeout=5
    )
    result = handle_response(resp)
    if isinstance(result, list):
        return result
    return []


def admin_delete_project(project_id: str) -> Dict:
    resp = requests.delete(
        f"{BACKEND_URL}/api/admin/projects/{project_id}",
        headers=_headers(),
        timeout=10
    )
    return handle_response(resp)


def health_check() -> Dict:
    try:
        resp = requests.get(f"{BACKEND_URL}/health", timeout=10)
        return handle_response(resp)
    except requests.exceptions.ConnectionError:
        return {"error": "Backend not reachable"}
    except Exception as e:
        return {"error": str(e)}


def export_markdown(project_id: str, persona: str = "both"):
    """Download docs as Markdown bytes. Call from main Streamlit thread only."""
    try:
        resp = requests.get(
            f"{BACKEND_URL}/api/projects/{project_id}/export/markdown",
            headers=_headers(),
            params={"persona": persona},
            timeout=30
        )
        if resp.status_code == 200:
            return resp.content
        print(f"[export_markdown] HTTP {resp.status_code}: {resp.text[:200]}")
        return None
    except Exception as exc:
        print(f"[export_markdown] error: {exc}")
        return None


def export_pdf(project_id: str, persona: str = "both"):
    """Download docs as PDF bytes. Call from main Streamlit thread only."""
    try:
        resp = requests.get(
            f"{BACKEND_URL}/api/projects/{project_id}/export/pdf",
            headers=_headers(),
            params={"persona": persona},
            timeout=60
        )
        if resp.status_code == 200:
            return resp.content
        print(f"[export_pdf] HTTP {resp.status_code}: {resp.text[:200]}")
        return None
    except Exception as exc:
        print(f"[export_pdf] error: {exc}")
        return None
