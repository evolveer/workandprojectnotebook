import os
import sys
import io
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Tuple

import pandas as pd
import streamlit as st

DB_PATH = Path(".worklog.db")
ATTACH_DIR = Path("attachments")
ATTACH_DIR.mkdir(exist_ok=True)

# ------------------------
# Utilities & DB Layer
# ------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            base_path TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            title TEXT NOT NULL,
            project_id INTEGER,
            work_type TEXT,
            tags TEXT,
            path TEXT,
            duration_hours REAL,
            notes_md TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            rel_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()
    conn.close()


def list_projects() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query("SELECT id, name, base_path, created_at FROM projects ORDER BY name", conn)
    conn.close()
    return df


def get_project_id_by_name(name: str) -> Optional[int]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM projects WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def upsert_project(name: str, base_path: Optional[str]):
    now = datetime.utcnow().isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM projects WHERE name = ?", (name,))
    if cur.fetchone():
        cur.execute("UPDATE projects SET base_path = ? WHERE name = ?", (base_path, name))
    else:
        cur.execute(
            "INSERT INTO projects(name, base_path, created_at) VALUES (?, ?, ?)",
            (name, base_path, now),
        )
    conn.commit()
    conn.close()


def insert_entry(ts: datetime, title: str, project_id: Optional[int], work_type: str,
                 tags: str, path: str, duration_hours: Optional[float], notes_md: str) -> int:
    now = datetime.utcnow().isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO entries(ts, title, project_id, work_type, tags, path, duration_hours, notes_md, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts.isoformat(), title, project_id, work_type, tags, path, duration_hours, notes_md, now),
    )
    entry_id = cur.lastrowid
    conn.commit()
    conn.close()
    return entry_id


def insert_attachment(entry_id: int, filename: str, rel_path: str):
    now = datetime.utcnow().isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO attachments(entry_id, filename, rel_path, created_at) VALUES (?, ?, ?, ?)",
        (entry_id, filename, rel_path, now),
    )
    conn.commit()
    conn.close()


def query_entries(
    start: Optional[date] = None,
    end: Optional[date] = None,
    project_ids: Optional[List[int]] = None,
    text: Optional[str] = None,
    tags_like: Optional[str] = None,
) -> pd.DataFrame:
    conn = get_conn()
    conditions = []
    params: List = []
    if start:
        conditions.append("DATE(ts) >= DATE(?)")
        params.append(start.isoformat())
    if end:
        conditions.append("DATE(ts) <= DATE(?)")
        params.append(end.isoformat())
    if project_ids:
        placeholders = ",".join(["?"] * len(project_ids))
        conditions.append(f"project_id IN ({placeholders})")
        params.extend(project_ids)
    if text:
        conditions.append("(title LIKE ? OR notes_md LIKE ? OR path LIKE ?)")
        like = f"%{text}%"
        params.extend([like, like, like])
    if tags_like:
        conditions.append("tags LIKE ?")
        params.append(f"%{tags_like}%")

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""
        SELECT e.id, e.ts, e.title, IFNULL(p.name, '') AS project, e.work_type,
               e.tags, e.path, e.duration_hours, e.notes_md
        FROM entries e
        LEFT JOIN projects p ON e.project_id = p.id
        {where}
        ORDER BY e.ts DESC
    """
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


def get_attachments(entry_id: int) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT id, filename, rel_path, created_at FROM attachments WHERE entry_id = ? ORDER BY id",
        conn,
        params=(entry_id,),
    )
    conn.close()
    return df


# ------------------------
# Helpers
# ------------------------

def datetime_picker(label: str, default: datetime) -> datetime:
    """Compatibility wrapper: use st.datetime_input if available,
    otherwise fall back to date_input + time_input.
    """
    if hasattr(st, "datetime_input"):
        return st.datetime_input(label, value=default)
    # Fallback for older Streamlit versions
    slug = label.lower().replace(" ", "_")
    d = st.date_input(f"{label} (date)", value=default.date(), key=f"{slug}_date")
    t = st.time_input(f"{label} (time)", value=default.time(), key=f"{slug}_time")
    return datetime.combine(d, t)


def do_rerun():
    """Compatibility wrapper for rerunning the app across Streamlit versions."""
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        do_rerun()
    else:
        st.warning("This Streamlit version doesn't support rerun(). Please update Streamlit.")


def human_path_link(p: str) -> str:
    p = os.path.expanduser(p)
    path_obj = Path(p)
    exists = path_obj.exists()
    safe_text = str(path_obj)
    # file:// links render clickable in Streamlit markdown
    link = f"file://{path_obj.as_posix()}"
    status = "✅" if exists else "⚠️"
    return f"{status} [{safe_text}]({link})"


def save_uploaded_files(entry_id: int, uploaded_files: List[io.BytesIO]) -> List[Tuple[str, str]]:
    saved = []
    base = ATTACH_DIR / f"entry_{entry_id}"
    base.mkdir(parents=True, exist_ok=True)
    for uf in uploaded_files or []:
        filename = uf.name
        dest = base / filename
        with open(dest, "wb") as f:
            f.write(uf.read())
        rel = dest.relative_to(Path.cwd())
        insert_attachment(entry_id, filename, str(rel))
        saved.append((filename, str(rel)))
    return saved


def open_in_os(path: str):
    """Attempt to open a file/folder in the OS file explorer.
    Works only when running locally with sufficient permissions."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
    except Exception as e:
        st.warning(f"Couldn't open path automatically: {e}")


# ------------------------
# UI Components
# ------------------------

def sidebar_projects():
    st.sidebar.subheader("Projects")
    df = list_projects()
    names = ["— none —"] + df["name"].tolist()
    selected = st.sidebar.selectbox("Active project", names, index=0)
    active_project_id = None
    active_project_base = ""
    if selected != "— none —":
        active_project_id = int(df[df.name == selected].iloc[0]["id"])  # type: ignore[index]
        active_project_base = str(df[df.name == selected].iloc[0]["base_path"])  # type: ignore[index]

    with st.sidebar.expander("Add / Update project", expanded=False):
        pname = st.text_input("Project name")
        pbase = st.text_input("Base path (optional)")
        if st.button("Save project", use_container_width=True):
            if not pname.strip():
                st.error("Project name is required")
            else:
                upsert_project(pname.strip(), pbase.strip() or None)
                st.success(f"Saved project '{pname}'")
                do_rerun()

    return active_project_id, active_project_base


def quick_capture(active_project_id: Optional[int], active_project_base: str):
    st.header("📝 Quick Capture")
    with st.form("quick_capture"):
        col1, col2 = st.columns([2,1])
        with col1:
            title = st.text_input("Title", placeholder="What did you do?")
        with col2:
            ts = datetime_picker("When", default=datetime.now())
        suggested_path = active_project_base or ""
        path = st.text_input("Workspace path", value=suggested_path, placeholder="/path/to/folder or file")
        if path and st.checkbox("Open this path after save"):
            st.session_state.setdefault("open_after_save", True)
        else:
            st.session_state["open_after_save"] = False
        work_type = st.selectbox("Type", [
            "Experiment", "Coding", "Analysis", "Planning", "Meeting", "Review", "Other"
        ])
        tags = st.text_input("Tags (comma-separated)")
        duration = st.number_input("Duration (hours)", min_value=0.0, step=0.25, value=0.0)
        notes = st.text_area("Notes (Markdown supported)", height=140)
        uploads = st.file_uploader("Attachments (optional)", accept_multiple_files=True)
        submitted = st.form_submit_button("Save entry", type="primary")

    if submitted:
        if not title.strip():
            st.error("Title is required.")
            return
        eid = insert_entry(
            ts=ts,
            title=title.strip(),
            project_id=active_project_id,
            work_type=work_type,
            tags=tags.strip(),
            path=path.strip(),
            duration_hours=float(duration) if duration else None,
            notes_md=notes,
        )
        saved = save_uploaded_files(eid, uploads)
        st.success(f"Saved entry #{eid}.")
        if st.session_state.get("open_after_save") and path.strip():
            open_in_os(path.strip())
        if saved:
            st.info(f"Saved {len(saved)} attachment(s).")


def recent_paths_widget():
    st.subheader("📂 Recent Paths")
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT DISTINCT path FROM entries WHERE path IS NOT NULL AND TRIM(path) != '' ORDER BY id DESC LIMIT 20",
        conn,
    )
    conn.close()
    if df.empty:
        st.caption("No paths yet. Add some via Quick Capture.")
        return
    for p in df["path"].tolist():
        cols = st.columns([6,1])
        with cols[0]:
            st.markdown(human_path_link(p), unsafe_allow_html=True)
        with cols[1]:
            if st.button("Open", key=f"open_{p}"):
                open_in_os(os.path.expanduser(p))


def entries_view():
    st.header("📚 Notebook Viewer & Search")
    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            start = st.date_input("Start", value=date.today() - timedelta(days=14))
        with col2:
            end = st.date_input("End", value=date.today())
        with col3:
            text = st.text_input("Search text")
        col4, col5 = st.columns(2)
        with col4:
            tags_like = st.text_input("Filter tag contains")
        with col5:
            # Multi-select projects
            projects_df = list_projects()
            proj_names = projects_df["name"].tolist()
            selected_names = st.multiselect("Projects", proj_names, default=proj_names)
            selected_ids = projects_df[projects_df["name"].isin(selected_names)]["id"].tolist()

    df = query_entries(start, end, selected_ids, text, tags_like)

    # Show compact table with expanders for details
    st.write(f"Found {len(df)} entries")
    if not df.empty:
        for _, row in df.iterrows():
            with st.expander(f"{row['ts']} • {row['title']} • {row['project']} • {row['work_type']}"):
                cols = st.columns([3,2])
                with cols[0]:
                    st.markdown(f"**Project:** {row['project']}")
                    st.markdown(f"**Type:** {row['work_type']}")
                    st.markdown(f"**Tags:** {row['tags']}")
                    st.markdown(f"**Duration:** {row['duration_hours'] if pd.notna(row['duration_hours']) else ''}")
                    if row['path']:
                        st.markdown("**Path:** " + human_path_link(row['path']), unsafe_allow_html=True)
                        if st.button("Open path", key=f"open_{row['id']}"):
                            open_in_os(os.path.expanduser(str(row['path'])))
                with cols[1]:
                    st.markdown("**Notes**")
                    st.markdown(row['notes_md'] or "")

                # Attachments
                att = get_attachments(int(row['id']))
                if not att.empty:
                    st.markdown("**Attachments**")
                    for _, arow in att.iterrows():
                        rel = arow['rel_path']
                        p = Path(rel)
                        if p.exists():
                            st.markdown(f"- [{arow['filename']}]({p.as_posix()})")
                        else:
                            st.markdown(f"- {arow['filename']} (missing: {rel})")

    # Export tools
    st.subheader("⬇️ Export")
    c1, c2 = st.columns(2)
    with c1:
        csv = df.drop(columns=["notes_md"]).to_csv(index=False).encode("utf-8") if not df.empty else b""
        st.download_button("Download CSV (no notes)", data=csv, file_name="worklog.csv", mime="text/csv")
    with c2:
        md = export_markdown(df)
        st.download_button("Download Markdown journal", data=md.encode("utf-8"), file_name="worklog.md", mime="text/markdown")


def export_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "# Worklog\n\n_No entries in the selected range._\n"
    df2 = df.copy()
    df2["date"] = pd.to_datetime(df2["ts"]).dt.date
    lines = ["# Worklog Export\n"]
    for d, g in df2.groupby("date", sort=True):
        lines.append(f"\n## {d}\n")
        for _, r in g.sort_values("ts").iterrows():
            title = r['title']
            proj = r['project']
            wt = r['work_type']
            tags = r['tags']
            path_str = human_path_link(r['path']) if r['path'] else ''
            dur = r['duration_hours'] if pd.notna(r['duration_hours']) else ''
            lines.append(f"### {title}\n")
            lines.append(f"- **Time:** {r['ts']}\n")
            if proj: lines.append(f"- **Project:** {proj}\n")
            if wt: lines.append(f"- **Type:** {wt}\n")
            if tags: lines.append(f"- **Tags:** {tags}\n")
            if path_str: lines.append(f"- **Path:** {path_str}\n")
            if dur != '': lines.append(f"- **Duration:** {dur} h\n")
            if r['notes_md']:
                lines.append("\n" + r['notes_md'] + "\n")
    return "\n".join(lines)


# ------------------------
# Page Layout
# ------------------------

def main():
    st.set_page_config(page_title="Lab Notebook Worklog", layout="wide")
    init_db()

    st.title("🧪 Lab Notebook — Work & Project Logger")
    st.caption("Log your project work quickly with paths, tags, and markdown notes. Data stays local in .worklog.db")

    active_project_id, active_project_base = sidebar_projects()

    # Top row: Quick Capture + Recent Paths
    lc, rc = st.columns([2,1])
    with lc:
        quick_capture(active_project_id, active_project_base)
    with rc:
        recent_paths_widget()

    st.divider()
    entries_view()

    with st.sidebar:
        st.divider()
        st.subheader("Utilities")
        if st.button("Open attachments folder"):
            open_in_os(str(ATTACH_DIR.resolve()))
        st.caption("Attachments are saved per-entry in ./attachments/")
        st.caption(f"Database: {DB_PATH.resolve()}")


if __name__ == "__main__":
    main()
