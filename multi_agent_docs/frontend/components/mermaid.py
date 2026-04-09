"""
Mermaid diagram renderer for Streamlit.
Fetches rendered PNG bytes from mermaid.ink server-side and passes them to st.image().
Using bytes (rather than a URL) ensures compatibility across all Streamlit versions
and provides clean error handling when diagrams fail to render.
"""
import base64
import streamlit as st
import requests as _req


def _fetch_diagram_bytes(mermaid_code: str, timeout: int = 15):
    """
    Fetch a rendered PNG from mermaid.ink for the given Mermaid code.
    Returns (bytes, None) on success, (None, error_str) on failure.
    """
    encoded = base64.urlsafe_b64encode(mermaid_code.strip().encode("utf-8")).decode("utf-8")
    url = f"https://mermaid.ink/img/{encoded}?theme=dark&bgColor=0e1117"
    try:
        resp = _req.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.content, None
        return None, f"mermaid.ink returned HTTP {resp.status_code}"
    except _req.exceptions.Timeout:
        return None, "Request to mermaid.ink timed out (>15 s)"
    except _req.exceptions.ConnectionError:
        return None, "Could not reach mermaid.ink — check internet connection"
    except Exception as e:
        return None, str(e)[:120]


def render_mermaid(mermaid_code: str, height: int = 450, key: str = None) -> None:
    """Render a Mermaid diagram. Falls back to source code if rendering fails."""
    if not mermaid_code or not mermaid_code.strip():
        st.warning("No diagram code available")
        return

    img_bytes, err = _fetch_diagram_bytes(mermaid_code)
    if img_bytes:
        st.image(img_bytes)
    else:
        st.warning(f"Diagram could not be rendered ({err}). Showing source below.")
        st.code(mermaid_code, language="text")


def render_mermaid_with_source(
    mermaid_code: str,
    title: str = "",
    description: str = "",
    height: int = 450,
    key: str = None,
) -> None:
    """Render a diagram with optional title/description and inline source."""
    if title:
        st.markdown(f"### {title}")
    if description:
        st.caption(description)

    if not mermaid_code or not mermaid_code.strip():
        st.warning("Diagram not available")
        return

    render_mermaid(mermaid_code, height=height, key=key)
    st.caption("Mermaid source")
    st.code(mermaid_code, language="text")


def validate_mermaid(code: str) -> tuple:
    """Basic client-side validation. Returns (is_valid, message)."""
    if not code or not code.strip():
        return False, "Empty diagram code"
    valid_starts = [
        "graph ", "graph\n", "flowchart ", "flowchart\n",
        "sequenceDiagram", "erDiagram", "classDiagram",
        "stateDiagram", "gantt", "pie", "gitgraph",
    ]
    if not any(code.strip().startswith(s) for s in valid_starts):
        return False, f"Must start with one of: {', '.join(valid_starts)}"
    return True, "OK"
