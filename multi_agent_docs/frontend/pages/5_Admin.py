"""
Admin Panel - User management, project management, system health, analytics.
"""
import streamlit as st
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

st.set_page_config(page_title="Admin Panel | CodeAnalyzer", page_icon="", layout="wide")

# Auth guard
if not st.session_state.get("token"):
    st.warning("Please login first")
    st.page_link("app.py", label="Go to Login")
    st.stop()

user = st.session_state.get("user", {})
if user.get("role") != "admin":
    st.error("Admin access required")
    st.caption("Only accounts with Admin role can access this panel.")
    st.stop()

from frontend.utils.api_client import (
    admin_get_stats, admin_list_users, admin_update_user, admin_delete_user,
    admin_list_projects, admin_delete_project
)

st.title("Admin Panel")
st.caption(f"Logged in as: **{user.get('username', 'Admin')}** · Admin")

tab_overview, tab_users, tab_projects, tab_health = st.tabs([
    "Overview", "User Management", "Project Management", "System Health"
])


# TAB 1: Overview / Stats
with tab_overview:
    st.markdown("### System Statistics")

    if st.button("Refresh Stats"):
        st.rerun()

    stats = admin_get_stats()
    if "error" in stats:
        st.error(f"Could not load stats: {stats['error']}")
    else:
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Total Users", stats.get("total_users", 0))
        with col2:
            st.metric("Total Projects", stats.get("total_projects", 0))
        with col3:
            st.metric("Active Analyses", stats.get("active_analyses", 0))
        with col4:
            st.metric("Completed", stats.get("completed_analyses", 0))
        with col5:
            st.metric("Failed", stats.get("failed_analyses", 0))

        if stats.get("total_projects", 0) > 0:
            completed = stats.get("completed_analyses", 0)
            total = stats.get("total_projects", 0)
            completion_rate = (completed / total) * 100
            st.metric("Completion Rate", f"{completion_rate:.1f}%")

    st.markdown("---")
    st.markdown("### Quick Analytics")

    projects = admin_list_projects()
    users = admin_list_users()

    if projects:
        import collections

        status_counts = collections.Counter(p.get("status", "unknown") for p in projects)
        st.markdown("**Project Status Distribution:**")
        for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
            pct = (count / len(projects)) * 100
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            st.text(f"{status:<15} {bar} {count} ({pct:.0f}%)")

        repo_types = [p.get("repo_type", "Unknown") for p in projects if p.get("repo_type")]
        if repo_types:
            st.markdown("**Repository Types:**")
            rt_counts = collections.Counter(
                t.split("(")[0].strip() if "(" in t else t for t in repo_types
            )
            for rt, count in rt_counts.most_common(5):
                st.text(f"  {rt}: {count}")


# TAB 2: User Management
with tab_users:
    st.markdown("### User Management")

    col_r, col_new = st.columns([1, 1])
    with col_r:
        if st.button("Refresh"):
            st.rerun()
    with col_new:
        st.caption("Use the main signup page to create new users")

    users = admin_list_users()
    if not users:
        st.info("No users found")
    else:
        st.caption(f"{len(users)} users registered")

        search = st.text_input("Search users", placeholder="Filter by name or email...")
        if search:
            users = [u for u in users if
                     search.lower() in u.get("email", "").lower() or
                     search.lower() in u.get("username", "").lower()]

        for user_row in users:
            uid = user_row.get("id", "")
            email = user_row.get("email", "")
            username = user_row.get("username", "")
            role = user_row.get("role", "user")
            is_active = user_row.get("is_active", True)
            created = user_row.get("created_at", "")[:10]

            role_color = "#f39c12" if role == "admin" else "#2ecc71"
            active_label = "Active" if is_active else "Inactive"

            with st.container():
                cols = st.columns([3, 1.5, 1, 1, 1, 1])
                with cols[0]:
                    st.markdown(f"**{username}** `{email}`")
                    st.caption(f"Created: {created}")
                with cols[1]:
                    st.markdown(f"<span style='color: {role_color};'>{role.upper()}</span>",
                                unsafe_allow_html=True)
                with cols[2]:
                    st.markdown(active_label)
                with cols[3]:
                    new_active = not is_active
                    label = "Disable" if is_active else "Enable"
                    if uid != st.session_state.user.get("id"):
                        if st.button(label, key=f"toggle_{uid}"):
                            result = admin_update_user(uid, {"is_active": new_active})
                            if "error" not in result:
                                st.success(f"User {label.lower()}d")
                                st.rerun()
                with cols[4]:
                    new_role = "user" if role == "admin" else "admin"
                    if uid != st.session_state.user.get("id"):
                        if st.button(f"Make {new_role.title()}", key=f"role_{uid}"):
                            result = admin_update_user(uid, {"role": new_role})
                            if "error" not in result:
                                st.success(f"Role changed to {new_role}")
                                st.rerun()
                with cols[5]:
                    if uid != st.session_state.user.get("id"):
                        if st.button("Delete", key=f"del_user_{uid}", help="Delete user"):
                            result = admin_delete_user(uid)
                            if "error" not in result:
                                st.success("User deleted")
                                st.rerun()
                            else:
                                st.error(result.get("error", ""))

            st.divider()


# TAB 3: Project Management
with tab_projects:
    st.markdown("### All Projects")

    if st.button("Refresh Projects"):
        st.rerun()

    all_projects = admin_list_projects()
    if not all_projects:
        st.info("No projects found")
    else:
        st.caption(f"{len(all_projects)} total projects across all users")

        status_filter = st.selectbox(
            "Filter by status",
            ["All", "completed", "analyzing", "paused", "failed", "ready", "created"],
            key="admin_project_filter"
        )
        if status_filter != "All":
            all_projects = [p for p in all_projects if p.get("status") == status_filter]

        STATUS_LABELS = {
            "completed": "Completed", "analyzing": "Analyzing", "preprocessing": "Preprocessing",
            "paused": "Paused", "failed": "Failed", "created": "Created", "ready": "Ready"
        }

        for proj in all_projects:
            pid = proj.get("id", "")
            name = proj.get("name", "Unknown")
            pstatus = proj.get("status", "unknown")
            progress = proj.get("progress", 0)
            repo_type = proj.get("repo_type", "")
            personas = proj.get("personas", [])
            user_id = proj.get("user_id", "")
            created = proj.get("created_at", "")[:10]

            with st.container():
                cols = st.columns([3, 1.5, 1, 1, 1, 1])
                with cols[0]:
                    st.markdown(f"**{name}**")
                    st.caption(f"ID: `{pid[:12]}...` · Owner: `{user_id[:8]}...` · {created}")
                    if repo_type:
                        st.caption(repo_type)
                with cols[1]:
                    st.markdown(STATUS_LABELS.get(pstatus, pstatus.title()))
                    st.caption(" · ".join(p.upper() for p in personas))
                with cols[2]:
                    st.caption(f"{progress}%")
                with cols[3]:
                    if st.button("Open", key=f"admin_open_{pid}"):
                        st.session_state.current_project_id = pid
                        if pstatus == "completed":
                            st.switch_page("pages/4_Documentation.py")
                        else:
                            st.switch_page("pages/3_Analysis.py")
                with cols[4]:
                    st.caption(f"{'SDE' if 'sde' in personas else ''} {'PM' if 'pm' in personas else ''}")
                with cols[5]:
                    if st.button("Delete", key=f"admin_del_proj_{pid}", help="Delete project"):
                        result = admin_delete_project(pid)
                        if "error" not in result:
                            st.success("Project deleted")
                            if st.session_state.get("current_project_id") == pid:
                                st.session_state.current_project_id = None
                            st.rerun()
                        else:
                            st.error(result.get("error", "Delete failed"))

                if pstatus == "failed" and proj.get("error_message"):
                    st.error(f"Error: {proj['error_message'][:150]}")

            st.divider()


# TAB 4: System Health
with tab_health:
    st.markdown("### System Health")

    if st.button("Check Health"):
        st.rerun()

    from frontend.utils.api_client import health_check
    health = health_check()

    if "error" in health:
        st.error(f"Backend unreachable: {health['error']}")
    else:
        st.success(f"Backend is **{health.get('status', 'unknown')}**")
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            st.metric("Service", health.get("service", ""))
            st.metric("Version", health.get("version", ""))
        with col_h2:
            st.metric("Active Analyses", health.get("active_analyses", 0))

    st.markdown("---")
    st.markdown("### System Information")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown("**Backend**")
        st.code("http://localhost:8000", language=None)
        st.markdown("**API Docs (Swagger)**")
        st.markdown("[Open Swagger UI](http://localhost:8000/docs)")
        st.markdown("[Open ReDoc](http://localhost:8000/redoc)")

    with col_s2:
        st.markdown("**Database**")
        st.caption("SQLite (no external service required)")
        st.markdown("**Vector Store**")
        st.caption("ChromaDB (in-process, no external service)")
        st.markdown("**LLM Provider**")
        llm_provider = os.environ.get("LLM_PROVIDER", "openai")
        llm_model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        st.caption(f"{llm_provider} / {llm_model}")

    st.markdown("---")
    st.markdown("### Langfuse Observability")
    langfuse_host = os.environ.get("LANGFUSE_HOST", "")
    langfuse_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    if langfuse_key and langfuse_host:
        st.success("Langfuse configured")
        st.markdown(f"[Open Langfuse Dashboard]({langfuse_host})")
    else:
        st.warning("Langfuse not configured. Set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST in .env")
        st.caption("Token tracking is still available via the Agent Traces tab in each project.")

    st.markdown("---")
    st.markdown("### Running Analyses")
    all_projects = admin_list_projects()
    active = [p for p in all_projects if p.get("status") in ("analyzing", "preprocessing", "paused")]
    if active:
        for proj in active:
            st.markdown(f"- **{proj['name']}** · {proj['status']} · {proj['progress']}%")
    else:
        st.info("No analyses currently running")
