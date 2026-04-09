"""
New Project Creation Page - Upload ZIP or GitHub URL, configure analysis.
"""
import streamlit as st
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

st.set_page_config(page_title="New Project | CodeAnalyzer", page_icon="", layout="wide")

# Auth guard
if not st.session_state.get("token"):
    st.warning("Please login first")
    st.page_link("app.py", label="Go to Login")
    st.stop()

from frontend.utils.api_client import create_project_with_upload, start_analysis

st.title("Create New Analysis Project")
st.caption("Upload a ZIP archive or provide a GitHub URL to start AI-powered documentation")

st.markdown("### Project Details")
col1, col2 = st.columns(2)
with col1:
    project_name = st.text_input(
        "Project Name *",
        placeholder="e.g. My FastAPI Backend",
        help="Give your project a descriptive name"
    )
with col2:
    project_desc = st.text_input(
        "Description (optional)",
        placeholder="Brief description of the codebase"
    )

st.markdown("### Repository Source")
source_type = st.radio(
    "Upload method",
    ["ZIP File", "GitHub URL"],
    horizontal=True,
    label_visibility="collapsed"
)

zip_file = None
github_url = ""

if source_type == "ZIP File":
    st.markdown("""
    <div style='background: #1a1d27; border: 1px dashed #4361ee; border-radius: 8px;
                padding: 1rem; margin: 0.5rem 0;'>
        <p style='color: #8899aa; margin: 0;'>
            Supported: <strong>.zip</strong> files only (max 100MB)<br>
            Not supported: .rar, .7z, .tar.gz formats<br>
            Must contain at least one code file (.py, .js, .ts, etc.)
        </p>
    </div>
    """, unsafe_allow_html=True)

    zip_file = st.file_uploader(
        "Choose ZIP file",
        type=["zip"],
        help="Upload your repository as a ZIP archive"
    )

    if zip_file:
        size_mb = len(zip_file.getvalue()) / (1024 * 1024)
        st.success(f"File ready: **{zip_file.name}** ({size_mb:.1f}MB)")

elif source_type == "GitHub URL":
    github_url = st.text_input(
        "GitHub Repository URL",
        placeholder="https://github.com/owner/repository",
        help="Public GitHub repositories only. Format: https://github.com/owner/repo"
    )
    if github_url:
        if github_url.startswith("https://github.com/") or github_url.startswith("http://github.com/"):
            st.success(f"GitHub URL: {github_url}")
        else:
            st.warning("URL should start with https://github.com/")

st.markdown("### Target Personas")
st.caption("Select who the documentation is for. Each persona gets a tailored report.")

col_sde, col_pm = st.columns(2)
with col_sde:
    sde_selected = st.checkbox(
        "Software Engineer (SDE)",
        value=True,
        help="Technical documentation: architecture, API docs, DB schema, setup guide, error handling"
    )
    if sde_selected:
        st.markdown("""
        <div style='background: #1a1d27; border-radius: 8px; padding: 0.8rem; font-size: 0.85rem; color: #8899aa;'>
        Includes:
        • Technical architecture overview<br>
        • API documentation with schemas<br>
        • Database schema & data models<br>
        • Setup & deployment guide<br>
        • Error handling & security patterns
        </div>
        """, unsafe_allow_html=True)

with col_pm:
    pm_selected = st.checkbox(
        "Product Manager (PM)",
        value=True,
        help="Business documentation: features, user flows, business logic, integrations"
    )
    if pm_selected:
        st.markdown("""
        <div style='background: #1a1d27; border-radius: 8px; padding: 0.8rem; font-size: 0.85rem; color: #8899aa;'>
        Includes:
        • Feature inventory<br>
        • User journey flows<br>
        • Business rules & logic<br>
        • Integration points<br>
        • Roadmap implications
        </div>
        """, unsafe_allow_html=True)

personas = []
if sde_selected:
    personas.append("sde")
if pm_selected:
    personas.append("pm")

if not personas:
    st.warning("Please select at least one persona")

st.markdown("### Analysis Configuration")
with st.expander("Configure agent behaviour", expanded=True):
    col_depth, col_verbosity = st.columns(2)
    with col_depth:
        depth = st.select_slider(
            "Analysis Depth",
            options=["quick", "standard", "deep"],
            value="standard",
            help="Quick: Fast scan | Standard: Thorough analysis | Deep: Comprehensive with all features"
        )
        depth_desc = {
            "quick": "Fast scan, core features only",
            "standard": "Balanced analysis, recommended",
            "deep": "Comprehensive analysis, all agents at full power"
        }
        st.caption(depth_desc[depth])

    with col_verbosity:
        verbosity = st.select_slider(
            "Documentation Verbosity",
            options=["low", "medium", "high"],
            value="medium",
            help="Controls detail level in generated documentation"
        )
        verb_desc = {
            "low": "Concise summaries",
            "medium": "Balanced detail (recommended)",
            "high": "Comprehensive with examples"
        }
        st.caption(verb_desc[verbosity])

    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        generate_diagrams = st.toggle(
            "Generate Mermaid Diagrams",
            value=True,
            help="Generate 5 visual diagrams: architecture, sequence, ER, flow, auth"
        )
        web_search = st.toggle(
            "Enable Web Research",
            value=True,
            help="Agents will search for latest best practices online"
        )
    with col_opt2:
        focus_areas_input = st.text_area(
            "Focus Areas (optional)",
            placeholder="e.g. authentication module\npayment processing\nAPI v2 endpoints",
            help="Enter specific areas to focus on, one per line",
            height=80
        )

    focus_areas = [f.strip() for f in focus_areas_input.split("\n") if f.strip()] if focus_areas_input else []

analysis_config = {
    "depth": depth,
    "verbosity": verbosity,
    "generate_diagrams": generate_diagrams,
    "web_search": web_search,
    "focus_areas": focus_areas
}

st.markdown("---")

can_submit = True
issues = []

if not project_name.strip():
    issues.append("Project name is required")
    can_submit = False

if source_type == "ZIP File" and not zip_file:
    issues.append("Please upload a ZIP file")
    can_submit = False
elif source_type == "GitHub URL" and not github_url.strip():
    issues.append("Please enter a GitHub URL")
    can_submit = False

if not personas:
    issues.append("Please select at least one persona")
    can_submit = False

if issues:
    for issue in issues:
        st.warning(issue)

col_submit, col_cancel = st.columns([2, 1])
with col_submit:
    submit_btn = st.button(
        "Create Project & Start Analysis",
        disabled=not can_submit,
        use_container_width=True,
        type="primary"
    )
with col_cancel:
    if st.button("Cancel", use_container_width=True):
        st.switch_page("pages/1_Dashboard.py")

if submit_btn and can_submit:
    with st.spinner("Creating project..."):
        result = create_project_with_upload(
            name=project_name.strip(),
            description=project_desc.strip(),
            personas=personas,
            analysis_config=analysis_config,
            zip_file=zip_file,
            github_url=github_url.strip()
        )

    if "error" in result:
        st.error(result['error'])
    else:
        project_id = result.get("id")
        st.success(f"Project created! ID: `{project_id}`")

        with st.spinner("Starting analysis..."):
            start_result = start_analysis(project_id)

        if "error" not in start_result:
            st.session_state.current_project_id = project_id
            st.success("Analysis started! Redirecting to monitor...")
            st.balloons()
            import time
            time.sleep(1.5)
            st.switch_page("pages/3_Analysis.py")
        else:
            st.warning(f"Project created but could not auto-start: {start_result.get('error', '')}")
            st.session_state.current_project_id = project_id
            st.info("Go to Dashboard to start the analysis manually.")
            if st.button("Go to Dashboard"):
                st.switch_page("pages/1_Dashboard.py")
