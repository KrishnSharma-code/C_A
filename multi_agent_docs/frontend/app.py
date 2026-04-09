"""
Main Streamlit Application - Login / Signup Entry Point
Multi-Agent Code Analysis & Documentation System
"""
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(
    page_title="CodeAnalyzer AI",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.stApp { background-color: #0e1117; }
.main .block-container { padding-top: 2rem; max-width: 900px; }

.auth-card {
    background: #1a1d27;
    border: 1px solid #2d3147;
    border-radius: 12px;
    padding: 2rem;
    margin: 0 auto;
}

.stButton > button {
    background-color: #4361ee;
    color: white;
    border-radius: 8px;
    border: none;
    font-weight: 500;
    transition: all 0.2s;
}
.stButton > button:hover { background-color: #3a56d4; transform: translateY(-1px); }

.stSuccess { background-color: #1a3a2a; border-left: 4px solid #2ecc71; }
.stError { background-color: #3a1a1a; border-left: 4px solid #e74c3c; }

.stTextInput > div > div > input {
    background-color: #1e2235;
    border: 1px solid #3d4166;
    color: #e0e0e0;
    border-radius: 8px;
}
.stSelectbox > div > div {
    background-color: #1e2235;
    border: 1px solid #3d4166;
}

.css-1d391kg, [data-testid="stSidebar"] {
    background-color: #12151e;
    border-right: 1px solid #2d3147;
}
</style>
""", unsafe_allow_html=True)

if "token" not in st.session_state:
    st.session_state.token = ""
if "user" not in st.session_state:
    st.session_state.user = None
if "current_project_id" not in st.session_state:
    st.session_state.current_project_id = None


def check_backend():
    """Check if backend is running."""
    try:
        from frontend.utils.api_client import health_check
        result = health_check()
        return "error" not in result
    except Exception:
        return False


def show_login():
    """Show login/signup form."""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style='text-align: center; margin-bottom: 2rem;'>
            <h1 style='color: #4361ee; font-size: 2.5rem;'>CodeAnalyzer AI</h1>
            <p style='color: #8899aa; font-size: 1rem;'>
                Multi-Agent Codebase Documentation System<br>
                <small>Python · FastAPI · LangGraph</small>
            </p>
        </div>
        """, unsafe_allow_html=True)

        if not check_backend():
            st.error("Backend not running. Start it with: `./run.sh` or `cd backend && uvicorn main:app --reload`")

        tab_login, tab_signup = st.tabs(["Login", "Sign Up"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email", placeholder="your@email.com")
                password = st.text_input("Password", type="password", placeholder="••••••••")
                submitted = st.form_submit_button("Login", use_container_width=True)

                if submitted:
                    if not email or not password:
                        st.error("Please fill in all fields")
                    else:
                        from frontend.utils.api_client import login
                        result = login(email, password)
                        if "error" in result:
                            st.error(f"Login failed: {result['error']}")
                        else:
                            st.session_state.token = result["access_token"]
                            st.session_state.user = result["user"]
                            st.success("Welcome back!")
                            st.rerun()

        with tab_signup:
            with st.form("signup_form"):
                new_email = st.text_input("Email", placeholder="your@email.com", key="signup_email")
                new_username = st.text_input("Username", placeholder="johndoe", key="signup_username")
                new_password = st.text_input("Password", type="password", placeholder="Min 6 characters", key="signup_password")
                new_role = st.selectbox("Role", ["user", "admin"], help="Admin has full system access")
                submitted = st.form_submit_button("Create Account", use_container_width=True)

                if submitted:
                    if not new_email or not new_username or not new_password:
                        st.error("Please fill in all fields")
                    elif len(new_password) < 6:
                        st.error("Password must be at least 6 characters")
                    elif len(new_username) < 3:
                        st.error("Username must be at least 3 characters")
                    else:
                        from frontend.utils.api_client import signup
                        result = signup(new_email, new_username, new_password, new_role)
                        if "error" in result:
                            st.error(f"Signup failed: {result['error']}")
                        else:
                            st.session_state.token = result["access_token"]
                            st.session_state.user = result["user"]
                            st.success("Account created! Welcome!")
                            st.rerun()

        st.markdown("""
        <div style='text-align: center; margin-top: 2rem; color: #555;'>
            <p>Supports Python, JavaScript, Go, Rust, Java & more</p>
            <p>ZIP upload or GitHub URL · SDE & PM documentation · 5+ AI agents</p>
        </div>
        """, unsafe_allow_html=True)


def show_sidebar():
    """Show navigation sidebar for logged-in users."""
    user = st.session_state.user
    with st.sidebar:
        st.markdown(f"""
        <div style='padding: 1rem 0; border-bottom: 1px solid #2d3147; margin-bottom: 1rem;'>
            <h3 style='color: #4361ee; margin: 0;'>CodeAnalyzer</h3>
            <p style='color: #8899aa; margin: 0.3rem 0 0 0; font-size: 0.85rem;'>
                {user.get('username', 'User')} · 
                <span style='color: {"#f39c12" if user.get("role") == "admin" else "#2ecc71"}'>
                    {user.get("role", "user").upper()}
                </span>
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.page_link("app.py", label="Home")
        st.page_link("pages/1_Dashboard.py", label="Dashboard")
        st.page_link("pages/2_New_Project.py", label="New Project")

        if st.session_state.current_project_id:
            st.markdown("---")
            st.markdown("**Current Project**")
            st.page_link("pages/3_Analysis.py", label="Analysis Monitor")
            st.page_link("pages/4_Documentation.py", label="Documentation")

        if user.get("role") == "admin":
            st.markdown("---")
            st.page_link("pages/5_Admin.py", label="Admin Panel")

        st.markdown("---")
        if st.button("Logout", use_container_width=True):
            st.session_state.token = ""
            st.session_state.user = None
            st.session_state.current_project_id = None
            st.rerun()


def show_home():
    """Show home page for logged-in users."""
    user = st.session_state.user
    st.title(f"Welcome, {user.get('username', 'User')}")

    from frontend.utils.api_client import list_projects
    projects = list_projects()

    col1, col2, col3, col4 = st.columns(4)
    total = len(projects)
    completed = sum(1 for p in projects if p.get("status") == "completed")
    active = sum(1 for p in projects if p.get("status") in ["analyzing", "preprocessing"])
    failed = sum(1 for p in projects if p.get("status") == "failed")

    with col1:
        st.metric("Total Projects", total)
    with col2:
        st.metric("Completed", completed)
    with col3:
        st.metric("Active", active)
    with col4:
        st.metric("Failed", failed)

    st.markdown("---")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("### Quick Actions")
        if st.button("Start New Analysis", use_container_width=True):
            st.switch_page("pages/2_New_Project.py")
        if st.button("View Dashboard", use_container_width=True):
            st.switch_page("pages/1_Dashboard.py")

    with col_r:
        st.markdown("### System Capabilities")
        st.markdown("""
        - **7 specialized AI agents** working in sequence
        - ZIP upload or **GitHub URL** import
        - **SDE & PM** persona-specific documentation  
        - **5 Mermaid diagram** types generated
        - Interactive **pause/resume** with Q&A
        - Semantic **code search** with vector embeddings
        - **PDF & Markdown** export
        """)

    if projects:
        st.markdown("### Recent Projects")
        for p in projects[:5]:
            with st.container():
                cols = st.columns([3, 1, 1, 1])
                with cols[0]:
                    st.write(f"**{p['name']}**")
                with cols[1]:
                    status_labels = {
                        "completed": "Completed",
                        "analyzing": "Analyzing",
                        "paused": "Paused",
                        "failed": "Failed",
                        "created": "Created",
                        "ready": "Ready",
                        "preprocessing": "Preprocessing"
                    }
                    st.write(status_labels.get(p['status'], p['status'].title()))
                with cols[2]:
                    st.write(f"{p.get('progress', 0)}%")
                with cols[3]:
                    if st.button("Open", key=f"home_open_{p['id']}"):
                        st.session_state.current_project_id = p["id"]
                        if p["status"] == "completed":
                            st.switch_page("pages/4_Documentation.py")
                        else:
                            st.switch_page("pages/3_Analysis.py")


if not st.session_state.token or not st.session_state.user:
    show_login()
else:
    show_sidebar()
    show_home()
