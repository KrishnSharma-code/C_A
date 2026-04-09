"""
Dashboard Page - Shows all user projects with status and quick actions.
"""
import streamlit as st
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

st.set_page_config(page_title="Dashboard | CodeAnalyzer", page_icon="", layout="wide")

# Auth guard
if not st.session_state.get("token"):
    st.warning("Please login first")
    st.page_link("app.py", label="Go to Login")
    st.stop()

from frontend.utils.api_client import list_projects, delete_project, start_analysis, get_project

st.title("Project Dashboard")

col_r1, col_r2 = st.columns([5, 1])
with col_r2:
    if st.button("Refresh"):
        st.rerun()
with col_r1:
    st.caption("Your projects and their analysis status")

projects = list_projects()

if not projects:
    st.info("No projects yet. Create your first analysis!")
    if st.button("Create New Project", use_container_width=True):
        st.switch_page("pages/2_New_Project.py")
    st.stop()

status_filter = st.selectbox(
    "Filter by status",
    ["All", "Completed", "Analyzing", "Paused", "Ready", "Failed"],
    index=0
)

filtered = projects
if status_filter != "All":
    filtered = [p for p in projects if p.get("status", "").lower() == status_filter.lower()]

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Total", len(projects))
with col2:
    st.metric("Completed", sum(1 for p in projects if p.get("status") == "completed"), delta_color="normal")
with col3:
    st.metric("Active", sum(1 for p in projects if p.get("status") in ["analyzing", "preprocessing"]))
with col4:
    st.metric("Paused", sum(1 for p in projects if p.get("status") == "paused"))
with col5:
    st.metric("Failed", sum(1 for p in projects if p.get("status") == "failed"))

st.markdown("---")

for project in filtered:
    pid = project["id"]
    status = project.get("status", "unknown")
    progress = project.get("progress", 0)
    personas = project.get("personas", [])
    repo_type = project.get("repo_type", "")

    STATUS_ICONS = {
        "completed": "Completed", "analyzing": "Analyzing", "preprocessing": "Preprocessing",
        "paused": "Paused", "failed": "Failed", "created": "Created", "ready": "Ready"
    }

    with st.container():
        st.markdown("""
        <div style='background: #1a1d27; border: 1px solid #2d3147; border-radius: 10px;
                    padding: 1rem; margin-bottom: 0.5rem;'>
        """, unsafe_allow_html=True)

        cols = st.columns([4, 1.5, 1.5, 1, 1, 1, 1])
        with cols[0]:
            name = project.get("name", "Unnamed")
            desc = project.get("description", "")
            st.markdown(f"**{name}**")
            if repo_type:
                st.caption(repo_type)
            if desc:
                st.caption(desc[:80])

        with cols[1]:
            st.markdown(f"**{status.title()}**")
            persona_badges = " ".join([f"`{p.upper()}`" for p in personas])
            st.markdown(persona_badges)

        with cols[2]:
            if status in ("analyzing", "preprocessing"):
                st.progress(progress / 100)
                st.caption(f"{progress}%")
            elif status == "completed":
                st.success("100% Complete")
            elif status == "paused":
                st.warning(f"Paused at {progress}%")
            elif status == "failed":
                st.error("Failed")
            else:
                st.caption("Not started")

        with cols[3]:
            if status == "ready":
                if st.button("Start", key=f"start_{pid}"):
                    result = start_analysis(pid)
                    if "error" not in result:
                        st.session_state.current_project_id = pid
                        st.success("Analysis started!")
                        st.rerun()
                    else:
                        st.error(result["error"])

        with cols[4]:
            if status in ("analyzing", "preprocessing", "paused"):
                if st.button("Monitor", key=f"monitor_{pid}"):
                    st.session_state.current_project_id = pid
                    st.switch_page("pages/3_Analysis.py")
            elif status == "completed":
                if st.button("View Docs", key=f"docs_{pid}"):
                    st.session_state.current_project_id = pid
                    st.switch_page("pages/4_Documentation.py")

        with cols[5]:
            if status == "completed":
                if st.button("Details", key=f"details_{pid}"):
                    st.session_state.current_project_id = pid
                    st.switch_page("pages/3_Analysis.py")

        with cols[6]:
            if st.button("Delete", key=f"del_{pid}", help="Delete project"):
                result = delete_project(pid)
                if "error" not in result:
                    if st.session_state.get("current_project_id") == pid:
                        st.session_state.current_project_id = None
                    st.success("Deleted")
                    st.rerun()
                else:
                    st.error(result.get("error", "Delete failed"))

        if status == "failed" and project.get("error_message"):
            st.error(f"Error: {project['error_message'][:200]}")

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("")

st.markdown("---")
if st.button("New Project", use_container_width=True):
    st.switch_page("pages/2_New_Project.py")
