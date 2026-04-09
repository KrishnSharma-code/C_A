"""
Analysis Monitor Page - Real-time progress, pause/resume, Q&A during analysis.
"""
import streamlit as st
import sys, os, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

st.set_page_config(page_title="Analysis | CodeAnalyzer", page_icon="", layout="wide")

# Auth guard
if not st.session_state.get("token"):
    st.warning("Please login first")
    st.page_link("app.py", label="Go to Login")
    st.stop()

from frontend.utils.api_client import (
    get_project, get_logs, pause_analysis, resume_analysis,
    add_context, get_traces, list_projects
)

project_id = st.session_state.get("current_project_id")

if not project_id:
    st.warning("No project selected")
    projects = list_projects()
    if projects:
        options = {f"{p['name']} ({p['status']})": p['id'] for p in projects}
        selected = st.selectbox("Select a project", list(options.keys()))
        if st.button("Open"):
            st.session_state.current_project_id = options[selected]
            st.rerun()
    else:
        if st.button("Create New Project"):
            st.switch_page("pages/2_New_Project.py")
    st.stop()

project = get_project(project_id)
if "error" in project:
    err_msg = project["error"]
    if "timed out" in err_msg.lower() or "busy" in err_msg.lower():
        st.warning(f"Backend is processing — {err_msg}")
        time.sleep(3)
        st.rerun()
    else:
        st.error(f"Could not load project: {err_msg}")
        st.stop()

status = project.get("status", "unknown")
progress = project.get("progress", 0)
current_agent = project.get("current_agent", "")
repo_type = project.get("repo_type", "")
project_name = project.get("name", "Unknown")

st.title("Analysis")
st.caption(f"Project: **{project_name}** · `{project_id[:8]}...`")

col_pause, col_resume, col_new, col_dash = st.columns(4)

with col_pause:
    if st.button("Pause", disabled=(status not in ("analyzing", "preprocessing")),
                 use_container_width=True):
        result = pause_analysis(project_id)
        if "error" not in result:
            st.success("Analysis paused")
            st.rerun()
        else:
            st.error(result.get("error", ""))

with col_resume:
    if st.button("Resume", disabled=(status != "paused"),
                 use_container_width=True):
        result = resume_analysis(project_id)
        if "error" not in result:
            st.success("Analysis resumed")
            st.rerun()
        else:
            st.error(result.get("error", ""))

with col_new:
    if st.button("New Project", use_container_width=True):
        st.switch_page("pages/2_New_Project.py")

with col_dash:
    if st.button("Dashboard", use_container_width=True):
        st.switch_page("pages/1_Dashboard.py")

if status == "completed":
    st.success("Completed — 100%")
elif status == "failed":
    err = project.get("error_message", "Unknown error")
    st.error(f"Analysis failed: {err[:200]}")
elif status == "paused":
    st.warning(f"Paused at {progress}%")
else:
    st.info(f"{status.title()}...")

progress_bar = st.progress(min(progress, 100) / 100)
if current_agent and status in ("analyzing", "preprocessing"):
    st.caption(f"Currently running: **{current_agent}**")

tab_feed, tab_qa, tab_traces = st.tabs(["Activity Feed", "Ask Questions", "Agent Traces"])

with tab_feed:
    logs = get_logs(project_id, limit=200)

    if logs:
        if repo_type:
            st.info(f"Detected: **{repo_type}**")

        LOG_STYLES = {
            "milestone": ("#2ecc71", "#1a3a2a"),
            "error": ("#e74c3c", "#3a1a1a"),
            "warning": ("#f39c12", "#3a2a1a"),
            "info": ("#3498db", "#1a2a3a"),
        }

        display_logs = list(reversed(logs[-50:]))

        for log in display_logs:
            level = log.get("level", "info")
            msg = log.get("message", "")
            agent = log.get("agent", "system")
            ts = log.get("timestamp", "")[:19].replace("T", " ")
            color, bg = LOG_STYLES.get(level, ("#3498db", "#1a2a3a"))

            st.markdown(f"""
            <div style='background: {bg}; border-left: 3px solid {color}; 
                        padding: 6px 10px; margin: 2px 0; border-radius: 4px;
                        font-size: 0.85rem;'>
                <span style='color: {color};'><strong>{agent}</strong></span>
                <span style='color: #ccc; margin-left: 8px;'>{msg}</span>
                <span style='color: #555; float: right; font-size: 0.75rem;'>{ts}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No activity yet. Start or resume analysis to see progress.")

    if status in ("analyzing", "preprocessing"):
        st.caption("Auto-refreshing every 3 seconds...")
        time.sleep(3)
        st.rerun()

with tab_qa:
    st.markdown("### Interactive Analysis Q&A")
    st.caption("Ask questions about the ongoing analysis or add context to guide the agents.")

    st.markdown("#### Ask About Analysis")
    with st.form("qa_during_analysis"):
        question = st.text_input(
            "Your question",
            placeholder="What are you analyzing right now? | What have you found so far? | Why is this taking so long?",
            label_visibility="collapsed"
        )
        col_ask, col_persona = st.columns([3, 1])
        with col_persona:
            qa_persona = st.selectbox("Perspective", ["sde", "pm"], label_visibility="collapsed")
        with col_ask:
            ask_btn = st.form_submit_button("Ask", use_container_width=True)

    if ask_btn and question.strip():
        with st.spinner("Thinking..."):
            from frontend.utils.api_client import ask_question
            result = ask_question(project_id, question.strip(), qa_persona)
        if "error" in result:
            st.error(result["error"])
        else:
            st.markdown(f"""
            <div style='background: #1a2a3a; border-radius: 8px; padding: 1rem; margin: 0.5rem 0;'>
                <p style='color: #8899aa; margin: 0 0 0.5rem 0; font-size: 0.85rem;'>
                    <strong>Q:</strong> {question}
                </p>
                <p style='color: #e0e0e0; margin: 0;'>{result.get("answer", "")}</p>
            </div>
            """, unsafe_allow_html=True)

            sources = result.get("sources", [])
            if sources:
                with st.expander("View source references"):
                    for src in sources:
                        st.caption(f"`{src.get('file', '')}` · {src.get('type', '')} · relevance: {src.get('relevance', 0):.0%}")

    st.markdown("---")

    st.markdown("#### Add Context to Analysis")
    st.caption("Inject additional information or instructions to guide ongoing analysis.")

    with st.form("add_context_form"):
        context_input = st.text_area(
            "Additional context",
            placeholder="Examples:\n• Focus more on the payment module\n• The authentication system uses OAuth2\n• This is a legacy system being migrated\n• The /admin routes are deprecated, focus on /api/v2",
            height=100,
            label_visibility="collapsed"
        )
        context_btn = st.form_submit_button("Add Context", use_container_width=True)

    if context_btn and context_input.strip():
        result = add_context(project_id, context_input.strip())
        if "error" not in result:
            st.success("Context added! Agents will incorporate this in their analysis.")
        else:
            st.error(result.get("error", "Failed to add context"))

    if status == "paused":
        st.markdown("---")
        st.info("Analysis is paused. Add context above, then resume.")
        with st.form("resume_with_context"):
            resume_context = st.text_input(
                "Context for resume (optional)",
                placeholder="Anything you want agents to know before continuing..."
            )
            if st.form_submit_button("Resume Analysis", use_container_width=True):
                result = resume_analysis(project_id, resume_context)
                if "error" not in result:
                    st.success("Analysis resumed!")
                    st.rerun()
                else:
                    st.error(result.get("error", ""))

with tab_traces:
    st.markdown("### Agent Execution Traces")
    st.caption("LLM token usage and performance metrics per agent")

    traces = get_traces(project_id)

    if traces:
        total_tokens = sum(t.get("total_tokens", 0) for t in traces)
        total_cost = sum(t.get("cost_usd", 0) for t in traces)
        avg_latency = sum(t.get("latency_ms", 0) for t in traces) / len(traces) if traces else 0

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Total Agents Called", len(traces))
        with m2:
            st.metric("Total Tokens", f"{total_tokens:,}")
        with m3:
            st.metric("Estimated Cost", f"${total_cost:.4f}")
        with m4:
            st.metric("Avg Latency", f"{avg_latency:.0f}ms")

        st.markdown("---")

        for trace in traces:
            agent_name = trace.get("agent_name", "unknown")
            in_tok = trace.get("input_tokens", 0)
            out_tok = trace.get("output_tokens", 0)
            total_tok = trace.get("total_tokens", 0)
            cost = trace.get("cost_usd", 0)
            latency = trace.get("latency_ms", 0)
            trace_status = trace.get("status", "success")
            ts = trace.get("created_at", "")[:19].replace("T", " ")

            status_color = "#2ecc71" if trace_status == "success" else "#e74c3c"

            if total_tok > 0:
                token_pct = (total_tok / max(total_tokens, 1)) * 100
                token_bar = "█" * int(token_pct / 5) + "░" * (20 - int(token_pct / 5))
            else:
                token_bar = ""

            st.markdown(f"""
            <div style='background: #1a1d27; border: 1px solid #2d3147; border-radius: 8px;
                        padding: 0.8rem; margin: 0.3rem 0;'>
                <div style='display: flex; justify-content: space-between;'>
                    <strong style='color: #4361ee;'>{agent_name}</strong>
                    <span style='color: {status_color}; font-size: 0.8rem;'>{trace_status}</span>
                </div>
                <div style='color: #8899aa; font-size: 0.8rem; margin-top: 4px;'>
                    {in_tok:,} input · {out_tok:,} output · 
                    {total_tok:,} total · ${cost:.4f} · {latency}ms
                </div>
                {f'<div style="color: #4361ee; font-family: monospace; font-size: 0.75rem;">{token_bar} {token_pct:.1f}%</div>' if token_bar else ''}
                <div style='color: #444; font-size: 0.75rem;'>{ts}</div>
            </div>
            """, unsafe_allow_html=True)

    else:
        st.info("No agent traces yet. Traces are recorded as agents complete their tasks.")

    langfuse_host = os.environ.get("LANGFUSE_HOST", "")
    if langfuse_host:
        st.markdown(f"[View in Langfuse Dashboard]({langfuse_host})")

if status == "completed":
    st.markdown("---")
    st.success("Analysis complete! Documentation is ready.")
    col_l, col_r = st.columns(2)
    with col_l:
        if st.button("View Documentation", use_container_width=True, type="primary"):
            st.switch_page("pages/4_Documentation.py")
    with col_r:
        if st.button("Back to Dashboard", use_container_width=True):
            st.switch_page("pages/1_Dashboard.py")
