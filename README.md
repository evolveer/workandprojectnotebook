

Lab Notebook — Work & Project Logger
====================================

This Streamlit app gives you a lightweight lab notebook for tracking daily work. Capture quick notes, associate them with projects, keep links to local files, attach artifacts, and review everything through a searchable timeline.

## Features
- Quick capture form with timestamps, tags, project selection, duration, and markdown notes
- Local SQLite database stored in `.worklog.db`; no cloud dependency
- Attachment support with per-entry folders inside `./attachments/`
- Searchable notebook view with date range filters, tag filtering, and exports to CSV or Markdown
- Convenience links to open saved paths or the attachments directory on your machine

## Prerequisites
- Python 3.9 or later
- pip (or another Python package manager)
- SQLite is bundled with Python and requires no extra setup

## Setup
1. (Recommended) Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
2. Install the Python dependencies:
   ```bash
   pip install streamlit pandas
   ```
   You can pin versions in a `requirements.txt` if you prefer:
   ```bash
   echo "streamlit\npandas" > requirements.txt
   pip install -r requirements.txt
   ```

## Run the App
```bash
streamlit run streamlit_work_project_lab_notebook_app.py
```
Streamlit will print a local URL (usually `http://localhost:8501`). Open it in your browser to start logging work.

## Data & Attachments
- Entries, projects, and metadata are stored locally in `.worklog.db` in the project root.
- Uploaded files are saved under `./attachments/entry_<id>/`.
- You can safely back up or version control both `.worklog.db` and the `attachments` folder if you want historical records.

## Tips
- Use the sidebar to create or update projects; paths entered there will pre-fill the capture form.
- The viewer lets you download a CSV without the long-form notes or a Markdown journal with all details.
- The “Open path” buttons rely on local OS tooling (`xdg-open`, `open`, or `start`); they work best when the app runs on the same machine as your files.

