"""
Documentation Page - SDE/PM reports, Diagrams, Q&A, Export.
"""
import streamlit as st
import sys, os
import threading
import time as _time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

st.set_page_config(page_title="Documentation | CodeAnalyzer", page_icon="", layout="wide")


def _run_with_progress(fn, label: str, estimated_secs: int, *args, **kwargs):
    """
    Run fn(*args, **kwargs) in a background thread while showing
    an animated progress bar and countdown timer in Streamlit.
    """
    result_box = [None]
    error_box  = [None]

    def _worker():
        try:
            result_box[0] = fn(*args, **kwargs)
        except Exception as exc:
            error_box[0] = str(exc)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    prog   = st.progress(0.0)
    status = st.empty()
    timer  = st.empty()
    t0     = _time.time()

    while thread.is_alive():
        elapsed   = _time.time() - t0
        frac      = min(elapsed / estimated_secs, 0.95)
        remaining = max(0.0, estimated_secs - elapsed)
        prog.progress(frac)
        status.caption(f"{label}")
        timer.markdown(f"**~{remaining:.0f}s** remaining")
        _time.sleep(0.4)

    prog.progress(1.0)
    _time.sleep(0.15)
    prog.empty()
    status.empty()
    timer.empty()

    if error_box[0]:
        return {"error": error_box[0]}
    return result_box[0]


# Auth guard
if not st.session_state.get("token"):
    st.warning("Please login first")
    st.page_link("app.py", label="Go to Login")
    st.stop()

from frontend.utils.api_client import (
    get_project, get_document_by_persona,
    get_diagrams, ask_question, get_qa_history,
    export_markdown, export_pdf, list_projects, search_code
)
from frontend.components.mermaid import render_mermaid

project_id = st.session_state.get("current_project_id")
if not project_id:
    st.warning("No project selected")
    projects = list_projects()
    completed = [p for p in projects if p.get("status") == "completed"]
    if completed:
        opts = {f"{p['name']}": p["id"] for p in completed}
        sel = st.selectbox("Select a completed project", list(opts.keys()))
        if st.button("Open"):
            st.session_state.current_project_id = opts[sel]
            st.rerun()
    else:
        st.info("No completed analyses yet.")
        if st.button("Create New Project"):
            st.switch_page("pages/2_New_Project.py")
    st.stop()

project = get_project(project_id)
if "error" in project:
    st.error(f"Could not load project: {project['error']}")
    st.stop()

status      = project.get("status", "unknown")
project_name = project.get("name", "Unknown")
personas    = project.get("personas", ["sde", "pm"])
repo_type   = project.get("repo_type", "Unknown")

st.title("Documentation")
col_title, col_controls = st.columns([3, 2])
with col_title:
    st.markdown(f"**{project_name}**")
    if repo_type:
        st.caption(f"{repo_type} · Personas: {', '.join(p.upper() for p in personas)}")

with col_controls:
    ca, cb = st.columns(2)
    with ca:
        if st.button("Analysis", use_container_width=True):
            st.switch_page("pages/3_Analysis.py")
    with cb:
        if st.button("Dashboard", use_container_width=True):
            st.switch_page("pages/1_Dashboard.py")

if status != "completed":
    if status in ("analyzing", "preprocessing", "paused"):
        st.warning(f"Analysis is {status}. Documentation may be incomplete.")
    elif status == "failed":
        st.error("Analysis failed. Some documentation may be unavailable.")
    else:
        st.info("Analysis not completed yet.")

st.markdown("---")

tab_sde, tab_pm, tab_diagrams, tab_qa, tab_export = st.tabs([
    "SDE Documentation",
    "PM Documentation",
    "Diagrams",
    "Q&A",
    "Export",
])


# TAB 1: SDE DOCUMENTATION
with tab_sde:
    if "sde" not in personas:
        st.info("SDE documentation was not selected for this project.")
    else:
        sde_doc = get_document_by_persona(project_id, "sde")
        if sde_doc:
            col_doc, col_qa = st.columns([3, 1])
            with col_qa:
                st.markdown("#### Quick Q&A")
                with st.form("sde_quick_qa"):
                    q = st.text_area("Ask about this doc", height=80,
                                     placeholder="How does auth work?\nWhat database is used?",
                                     label_visibility="collapsed")
                    if st.form_submit_button("Ask", use_container_width=True):
                        if q.strip():
                            _tok = st.session_state.get("token", "")
                            result = _run_with_progress(
                                ask_question,
                                "Searching documentation and generating answer...",
                                30,
                                project_id, q.strip(), "sde", _tok
                            )
                            if result and "error" in result:
                                st.error(result["error"])
                            elif result:
                                st.session_state["sde_qa_answer"]   = result.get("answer", "")
                                st.session_state["sde_qa_question"] = q.strip()

                if st.session_state.get("sde_qa_answer"):
                    st.markdown(f"**Q:** {st.session_state.get('sde_qa_question', '')}")
                    st.markdown(st.session_state["sde_qa_answer"])

            with col_doc:
                st.markdown(sde_doc.get("content", ""))
        else:
            msg = ("SDE documentation not found. The analysis may not have completed."
                   if status == "completed" else
                   "SDE documentation will appear here once analysis completes.")
            st.warning(msg) if status == "completed" else st.info(msg)


# TAB 2: PM DOCUMENTATION
with tab_pm:
    if "pm" not in personas:
        st.info("PM documentation was not selected for this project.")
    else:
        pm_doc = get_document_by_persona(project_id, "pm")
        if pm_doc:
            col_doc, col_qa = st.columns([3, 1])
            with col_qa:
                st.markdown("#### Quick Q&A")
                st.caption("Ask in business terms")
                with st.form("pm_quick_qa"):
                    q = st.text_area("Ask about features", height=80,
                                     placeholder="What are the main features?\nHow does the user flow work?",
                                     label_visibility="collapsed")
                    if st.form_submit_button("Ask", use_container_width=True):
                        if q.strip():
                            _tok = st.session_state.get("token", "")
                            result = _run_with_progress(
                                ask_question,
                                "Searching documentation and generating answer...",
                                30,
                                project_id, q.strip(), "pm", _tok
                            )
                            if result and "error" in result:
                                st.error(result["error"])
                            elif result:
                                st.session_state["pm_qa_answer"]   = result.get("answer", "")
                                st.session_state["pm_qa_question"] = q.strip()

                if st.session_state.get("pm_qa_answer"):
                    st.markdown(f"**Q:** {st.session_state.get('pm_qa_question', '')}")
                    st.markdown(st.session_state["pm_qa_answer"])

            with col_doc:
                st.markdown(pm_doc.get("content", ""))
        else:
            msg = ("PM documentation not found. Ensure 'PM' persona was selected."
                   if status == "completed" else
                   "PM documentation will appear here once analysis completes.")
            st.warning(msg) if status == "completed" else st.info(msg)


# TAB 3: DIAGRAMS
with tab_diagrams:
    diagrams = get_diagrams(project_id)

    if not diagrams:
        msg = ("No diagrams found. Diagram generation may have been disabled or failed."
               if status == "completed" else
               "Diagrams will appear here once analysis completes.")
        st.warning(msg) if status == "completed" else st.info(msg)
    else:
        st.markdown(f"**{len(diagrams)} diagrams generated**")
        st.caption("Rendered via mermaid.ink · requires internet connection")

        DIAGRAM_ORDER = {"architecture": 0, "sequence": 1, "er_diagram": 2,
                         "user_flow": 3, "auth_flow": 4}
        sorted_diagrams = sorted(
            diagrams,
            key=lambda d: DIAGRAM_ORDER.get(d.get("diagram_type", ""), 99)
        )

        for diagram in sorted_diagrams:
            dtype        = diagram.get("diagram_type", "diagram")
            title        = diagram.get("title", dtype.replace("_", " ").title())
            description  = diagram.get("description", "")
            mermaid_code = diagram.get("mermaid_code", "")
            persona      = diagram.get("persona", "both")

            persona_label = {"sde": "SDE", "pm": "PM", "both": "All"}.get(persona, "All")

            with st.expander(f"**{title}** · {persona_label}", expanded=True):
                if description:
                    st.caption(description)

                if mermaid_code and mermaid_code.strip():
                    render_mermaid(
                        mermaid_code=mermaid_code,
                        height=450,
                        key=f"diag_{diagram.get('id', dtype)}"
                    )
                    st.caption("Mermaid source")
                    st.code(mermaid_code, language="text")
                else:
                    st.warning("Diagram code is empty")


# TAB 4: Q&A
with tab_qa:
    st.markdown("### Ask Questions About the Codebase")
    st.caption("Powered by semantic search + AI. Requires OPENAI_API_KEY in .env")

    col_input, col_settings = st.columns([4, 1])
    with col_settings:
        qa_persona = st.selectbox(
            "Perspective",
            ["sde", "pm"],
            format_func=lambda x: "SDE (Technical)" if x == "sde" else "PM (Business)"
        )
    with col_input:
        with st.form("qa_form", clear_on_submit=True):
            question = st.text_input(
                "Your question",
                placeholder="How does authentication work? | What are the main API endpoints?",
                label_visibility="collapsed"
            )
            ask_btn = st.form_submit_button("Ask", use_container_width=True)

    if ask_btn and question.strip():
        _tok = st.session_state.get("token", "")
        result = _run_with_progress(
            ask_question,
            "Searching documentation and codebase, generating answer...",
            30,
            project_id, question.strip(), qa_persona, _tok
        )

        if "error" in result:
            st.error(f"Q&A failed: {result['error']}")
        else:
            answer = result.get("answer", "")
            st.markdown(
                f"""<div style='background:#1a2a3a;border-left:4px solid #4361ee;
                border-radius:8px;padding:1.2rem;margin:1rem 0'>
                <p style='color:#8899aa;margin:0 0 .5rem;font-size:.85rem'>
                <em>{question}</em></p>
                <div style='color:#e0e0e0'>{answer.replace(chr(10),'<br>')}</div>
                </div>""",
                unsafe_allow_html=True,
            )
            sources = result.get("sources", [])
            if sources:
                st.markdown("**Referenced files:**")
                for src in sources:
                    st.caption(f"`{src.get('file','')}` · {src.get('type','')} · {src.get('relevance',0):.0%} relevance")

    st.markdown("---")
    st.markdown("### Q&A History")
    history = get_qa_history(project_id)
    if history:
        for entry in history[:20]:
            with st.expander(f"**{entry.get('question','')[:80]}**"):
                st.markdown(f"**Persona:** {entry.get('persona','').upper()}")
                st.markdown(f"**Answer:**\n{entry.get('answer','')}")
                srcs = entry.get("sources", [])
                if srcs:
                    st.caption(f"Sources: {', '.join(s.get('file','') for s in srcs[:3])}")
    else:
        st.caption("No questions asked yet.")

    st.markdown("---")
    st.markdown("### Semantic Code Search")
    st.caption("Find relevant code sections by natural language description")
    with st.form("search_form", clear_on_submit=True):
        search_q = st.text_input(
            "Search codebase",
            placeholder="JWT authentication | database connection | API endpoint handler",
            label_visibility="collapsed"
        )
        search_btn = st.form_submit_button("Search", use_container_width=True)

    if search_btn and search_q.strip():
        with st.spinner("Searching..."):
            results = search_code(project_id, search_q.strip())
        if "error" in results:
            st.error(results["error"])
        elif results.get("results"):
            for i, chunk in enumerate(results["results"]):
                meta    = chunk.get("metadata", {})
                content = chunk.get("content", "")
                score   = chunk.get("relevance_score", 0)
                with st.expander(f"Result {i+1}: `{meta.get('file_path','')}` · {score:.0%} match"):
                    st.code(content[:500], language=meta.get("language", "text"))
                    st.caption(f"Type: {meta.get('type','')} · Lines: {meta.get('start_line','')}-{meta.get('end_line','')}")
        else:
            st.info("No matching code sections found.")


# TAB 5: EXPORT
with tab_export:
    st.markdown("### Export Documentation")

    persona_option = st.radio(
        "Export scope",
        ["both", "sde", "pm"],
        format_func=lambda x: "Both (SDE + PM)" if x == "both" else ("SDE Only" if x == "sde" else "PM Only"),
        horizontal=True
    )

    col_md, col_pdf = st.columns(2)

    with col_md:
        st.markdown("#### Markdown")
        st.caption("Full documentation as a single Markdown file, including Mermaid source.")

        if st.button("Prepare Markdown", use_container_width=True, key="btn_md"):
            with st.spinner("Compiling documentation into Markdown..."):
                md_bytes = export_markdown(project_id, persona_option)
            if md_bytes:
                st.session_state["md_export_bytes"]   = md_bytes
                st.session_state["md_export_persona"] = persona_option
            else:
                st.error("Markdown export failed. Ensure analysis is complete.")

        if st.session_state.get("md_export_bytes"):
            st.download_button(
                "Download Markdown",
                data=st.session_state["md_export_bytes"],
                file_name=f"{project_name}_documentation.md",
                mime="text/markdown",
                use_container_width=True,
                key="dl_md"
            )

    with col_pdf:
        st.markdown("#### PDF")
        st.caption("Professionally formatted PDF with all sections and code blocks.")

        if st.button("Generate PDF", use_container_width=True, key="btn_pdf"):
            with st.spinner("Generating PDF (formatting + layout)..."):
                pdf_bytes = export_pdf(project_id, persona_option)
            if pdf_bytes:
                st.session_state["pdf_export_bytes"]   = pdf_bytes
                st.session_state["pdf_export_persona"] = persona_option
            else:
                st.error("PDF generation failed. Check server logs.")

        if st.session_state.get("pdf_export_bytes"):
            st.download_button(
                "Download PDF",
                data=st.session_state["pdf_export_bytes"],
                file_name=f"{project_name}_documentation.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="dl_pdf"
            )

    st.markdown("---")
    st.markdown("### Documentation Preview")
    prev_sde, prev_pm = st.tabs(["SDE Preview", "PM Preview"])

    with prev_sde:
        if "sde" in personas:
            sde_doc = get_document_by_persona(project_id, "sde")
            if sde_doc:
                content = sde_doc.get("content", "")
                st.markdown(content[:3000] + ("\n\n*[Document truncated for preview]*" if len(content) > 3000 else ""))
            else:
                st.info("SDE documentation not available.")
        else:
            st.info("SDE persona was not selected.")

    with prev_pm:
        if "pm" in personas:
            pm_doc = get_document_by_persona(project_id, "pm")
            if pm_doc:
                content = pm_doc.get("content", "")
                st.markdown(content[:3000] + ("\n\n*[Document truncated for preview]*" if len(content) > 3000 else ""))
            else:
                st.info("PM documentation not available.")
        else:
            st.info("PM persona was not selected.")
