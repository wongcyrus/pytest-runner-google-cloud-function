import os
import json
import html
from datetime import datetime, timezone
import functions_framework
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from google.cloud import storage
import openpyxl

def get_students_from_excel(filepath: str) -> list[dict]:
    """Reads student IDs and names from the bundled Namelist.xlsx."""
    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found.")
        return []
    
    wb = openpyxl.load_workbook(filepath)
    ws = wb.active
    students = []
    for row in ws.iter_rows(min_row=2, max_col=2, values_only=True):
        if row[0] is not None:
            student_id = str(row[0]).strip()
            student_name = str(row[1]).strip() if row[1] is not None else ""
            students.append({"id": student_id, "name": student_name})
    return students

def get_completed_tasks_for_student(db: firestore.Client, student_id: str) -> list[str]:
    """Retrieves list of completed tasks for a specific student."""
    completed_tasks_ref = db.collection("CompletedTask")
    query = completed_tasks_ref.where(filter=FieldFilter("student_id", "==", str(student_id)))
    docs = list(query.stream())
    results = [task.to_dict().get("question") for task in docs if task.to_dict()]
    results = [q for q in results if q is not None]
    results.sort()
    return results

def generate_html_report(student_data: list[dict], all_tasks: list[str], generated_at: str) -> str:
    """Generates a responsive and modern HTML report displaying Student Names and Scores."""
    total_students = len(student_data)
    total_tasks = len(all_tasks)
    total_completions = sum(len(s["tasks"]) for s in student_data)
    avg_score = round(total_completions / total_students, 2) if total_students > 0 else 0

    task_headers_html = "".join(
        f'<th class="task-col" title="{html.escape(t)}">{html.escape(t.replace("task", "T#") if t.startswith("task") else t)}</th>'
        for t in all_tasks
    )

    rows_html = []
    for s in student_data:
        name = html.escape(s.get("name") or s.get("id"))
        tasks_completed = s.get("tasks", [])
        score = len(tasks_completed)

        task_cells = []
        for t in all_tasks:
            if t in tasks_completed:
                task_cells.append('<td class="status-cell completed" title="Completed">✓</td>')
            else:
                task_cells.append('<td class="status-cell pending" title="Not completed">-</td>')

        row = f"""
        <tr>
            <td class="student-name">{name}</td>
            <td class="score-cell">
                <span class="score-badge">{score}</span>
            </td>
            {''.join(task_cells)}
        </tr>
        """
        rows_html.append(row)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pytest Runner - Score Report</title>
    <style>
        :root {{
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --primary: #3b82f6;
            --primary-dark: #1d4ed8;
            --success: #10b981;
            --success-bg: #d1fae5;
            --border-color: #e2e8f0;
            --row-hover: #f1f5f9;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            padding: 2rem 1.5rem;
            line-height: 1.5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .header {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 1.5rem 2rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
        }}
        .header h1 {{
            font-size: 1.75rem;
            font-weight: 700;
            color: var(--text-primary);
        }}
        .header .meta {{
            color: var(--text-secondary);
            font-size: 0.875rem;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }}
        .stat-card {{
            background: var(--card-bg);
            border-radius: 10px;
            padding: 1.25rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            border: 1px solid var(--border-color);
        }}
        .stat-card .label {{
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin-bottom: 0.25rem;
        }}
        .stat-card .value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--primary);
        }}
        .table-card {{
            background: var(--card-bg);
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            overflow: hidden;
            border: 1px solid var(--border-color);
        }}
        .table-responsive {{
            overflow-x: auto;
            max-height: 70vh;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
            text-align: left;
        }}
        thead {{
            position: sticky;
            top: 0;
            background: #f1f5f9;
            z-index: 10;
        }}
        th {{
            padding: 0.85rem 1rem;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-size: 0.75rem;
            border-bottom: 2px solid var(--border-color);
            white-space: nowrap;
        }}
        th.task-col {{
            text-align: center;
            min-width: 50px;
        }}
        tbody tr {{
            border-bottom: 1px solid var(--border-color);
            transition: background-color 0.15s ease;
        }}
        tbody tr:hover {{
            background-color: var(--row-hover);
        }}
        td {{
            padding: 0.75rem 1rem;
            white-space: nowrap;
        }}
        .student-name {{
            font-weight: 600;
            color: var(--text-primary);
            position: sticky;
            left: 0;
            background: inherit;
            z-index: 1;
        }}
        .score-cell {{
            min-width: 140px;
        }}
        .score-badge {{
            display: inline-block;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 0.25rem;
        }}
        .progress-bar-bg {{
            height: 6px;
            background: #e2e8f0;
            border-radius: 3px;
            overflow: hidden;
            width: 100%;
        }}
        .progress-bar-fill {{
            height: 100%;
            background: var(--success);
            border-radius: 3px;
            transition: width 0.3s ease;
        }}
        .status-cell {{
            text-align: center;
            font-size: 1rem;
            font-weight: bold;
        }}
        .status-cell.completed {{
            color: var(--success);
            background-color: rgba(16, 185, 129, 0.08);
        }}
        .status-cell.pending {{
            color: #cbd5e1;
        }}
        .footer {{
            margin-top: 1.5rem;
            text-align: center;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>Student Score Report</h1>
                <p class="meta">Automated daily task completion breakdown</p>
            </div>
            <div class="meta">
                Last updated: <strong>{generated_at}</strong>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Total Students</div>
                <div class="value">{total_students}</div>
            </div>
            <div class="stat-card">
                <div class="label">Average Completed Tasks</div>
                <div class="value">{avg_score}</div>
            </div>
            <div class="stat-card">
                <div class="label">Total Completed Submissions</div>
                <div class="value">{total_completions}</div>
            </div>
        </div>

        <div class="table-card">
            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th style="position: sticky; left: 0; background: #f1f5f9; z-index: 11;">Student Name</th>
                            <th>Completed Tasks</th>
                            {task_headers_html}
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows_html)}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="footer">
            Pytest Runner Score Dashboard &bull; Generated automatically via Google Cloud Scheduler
        </div>
    </div>
</body>
</html>
"""
    return html_content

def upload_to_bucket(bucket_name: str, filename: str, content: str):
    """Uploads the generated HTML content to the GCS website bucket."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(filename)
    blob.cache_control = "no-cache, max-age=0"
    blob.upload_from_string(content, content_type="text/html")
    print(f"Successfully uploaded {filename} to gs://{bucket_name}/")

@functions_framework.http
def scorereport(request):
    """HTTP Cloud Function that generates and uploads the daily score report."""
    bucket_name = os.environ.get("REPORT_BUCKET")
    if not bucket_name:
        return ("Environment variable REPORT_BUCKET is not set", 500)

    namelist_path = os.path.join(os.path.dirname(__file__), "Namelist.xlsx")
    students = get_students_from_excel(namelist_path)

    db = firestore.Client(database="pytestrunner")
    try:
        # Fallback to ApiKey collection if Namelist.xlsx was empty
        if not students:
            api_keys_ref = db.collection("ApiKey")
            api_keys = list(api_keys_ref.order_by("student_id").stream())
            students = [
                {
                    "id": str(doc.to_dict().get("student_id", "")),
                    "name": str(doc.to_dict().get("name") or doc.to_dict().get("student_id", ""))
                }
                for doc in api_keys
                if doc.to_dict().get("student_id")
            ]

        # Gather completed tasks for each student
        student_data = []
        for s in students:
            tasks = get_completed_tasks_for_student(db, s["id"])
            student_data.append({
                "id": s["id"],
                "name": s["name"],
                "tasks": tasks
            })

        # Sort students alphabetically by name (or id)
        student_data.sort(key=lambda item: item["name"] or item["id"])

        # Determine all unique tasks
        all_tasks = sorted(list(set().union(*[s["tasks"] for s in student_data]))) if student_data else []

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        html_report = generate_html_report(student_data, all_tasks, now_utc)

        upload_to_bucket(bucket_name, "index.html", html_report)

        return (json.dumps({
            "status": "success",
            "students_count": len(student_data),
            "tasks_count": len(all_tasks),
            "generated_at": now_utc,
            "bucket": bucket_name
        }), 200, {"Content-Type": "application/json"})

    finally:
        try:
            db.close()
        except Exception:
            pass
