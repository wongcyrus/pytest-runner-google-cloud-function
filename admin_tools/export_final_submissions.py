import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import zipfile
import uuid

from google.cloud import firestore, storage
from openpyxl import Workbook

from config import project_id


def read_collection(db, name):
    return [doc.to_dict() for doc in db.collection(name).stream()]


def workbook_bytes(rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
        for cell in ws[ws.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def read_source(record, storage_client):
    reference = record.get("source_ref")
    if reference:
        if storage_client is None:
            raise ValueError("A storage client is required for GCS source records")
        generation = reference.get("generation")
        blob = storage_client.bucket(reference["bucket"]).blob(
            reference["object"], generation=int(generation) if generation is not None else None)
        code = blob.download_as_bytes(
            if_generation_match=int(generation) if generation is not None else None)
        if reference.get("sha256") and hashlib.sha256(code).hexdigest() != reference["sha256"]:
            raise ValueError(f"Source checksum mismatch: {reference['object']}")
        code.decode("utf-8")
        return code, "complete"
    code = record.get("source_code")
    if code is None:
        return None, "missing"
    return code.encode("utf-8"), (
        "complete" if record.get("source_code_complete") else "possibly_truncated")


def export_archive(api_keys, completed, latest, output, project=None, lab=None,
                   storage_client=None):
    if lab:
        def matches(record):
            return lab in record["question"].replace("\\", "/").split("/")[:-1]
        completed = [record for record in completed if matches(record)]
        latest = [record for record in latest if matches(record)]
    students = {str(record["student_id"]) for record in api_keys if "student_id" in record}
    earned = {(str(record["student_id"]), record["question"]) for record in completed}
    submissions = {}
    passing = {}
    for record in completed:
        key = (str(record["student_id"]), record["question"])
        submissions[key] = dict(record, status=record.get("status", "legacy_pass"))
        passing[key] = record
    for record in latest:
        key = (str(record["student_id"]), record["question"])
        submissions[key] = record
    students.update(student for student, _ in earned | set(submissions))
    tasks = sorted({task for _, task in earned | set(submissions)})
    scores = [["id", "score", *tasks]]
    for student in sorted(students):
        marks = [int((student, task) in earned) for task in tasks]
        scores.append([student, sum(marks), *marks])

    rows = [["id", "question", "earned_mark", "latest_status", "time",
             "code_completeness", "code_file", "passed_tests", "total_tests",
             "passed_code_file", "passed_code_completeness", "passed_time",
             "latest_source_ref", "passed_source_ref", "submission_id",
             "passed_submission_id", "is_project", "earned_time"]]
    manifest = []
    output = Path(output)
    partial = output.with_name(output.name + "." + uuid.uuid4().hex + ".partial")
    try:
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            _write_archive(archive, submissions, passing, earned, scores, rows, manifest,
                           storage_client, project, lab, students)
        partial.replace(output)
    finally:
        partial.unlink(missing_ok=True)
    return len(students), len(submissions)


def _write_archive(archive, submissions, passing, earned, scores, rows, manifest,
                   storage_client, project, lab, students):
    for (student, task), record in sorted(submissions.items()):
        code, completeness = read_source(record, storage_client)
        code_file = ""
        student_hash = hashlib.sha256(student.encode("utf-8")).hexdigest()
        task_hash = hashlib.sha256(task.encode("utf-8")).hexdigest()
        if code is not None:
            code_file = f"latest/{student_hash}/{task_hash}.py"
            archive.writestr(code_file, code)
        passed_record = passing.get((student, task), {})
        passed_code, passed_completeness = read_source(passed_record, storage_client)
        passed_file = ""
        if passed_code is not None:
            passed_file = f"passed/{student_hash}/{task_hash}.py"
            archive.writestr(passed_file, passed_code)
        passed_time = passed_record.get("submitted_at", passed_record.get("time"))
        passed_time = passed_time.isoformat() if passed_time is not None else ""
        earned_time = passed_record.get("time")
        earned_time = earned_time.isoformat() if earned_time is not None else ""
        timestamp = record.get("submitted_at", record.get("time"))
        timestamp = timestamp.isoformat() if timestamp is not None else ""
        summary = record.get("summary") or {}
        entry = {
            "id": student, "question": task, "earned_mark": int((student, task) in earned),
            "latest_status": record.get("status", "unknown"), "time": timestamp,
            "code_completeness": completeness, "code_file": code_file,
            "passed_tests": summary.get("passed"), "total_tests": summary.get("total"),
            "passed_code_file": passed_file,
            "passed_code_completeness": passed_completeness,
            "passed_time": passed_time,
            "latest_source_ref": record.get("source_ref"),
            "passed_source_ref": passed_record.get("source_ref"),
            "submission_id": record.get("submission_id"),
            "passed_submission_id": passed_record.get("submission_id"),
            "is_project": record.get("is_project"),
            "earned_time": earned_time,
        }
        manifest.append(entry)
        rows.append([json.dumps(value) if isinstance(value, dict) else value
                     for value in entry.values()])
    archive.writestr("scores.xlsx", workbook_bytes(scores))
    archive.writestr("submissions.xlsx", workbook_bytes(rows))
    archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    archive.writestr("export_info.json", json.dumps({
        "project": project,
        "database": "pytestrunner",
        "lab": lab,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "students": len(students),
        "submissions": len(submissions),
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Export earned marks, latest code and latest passing code from Firestore/GCS.")
    parser.add_argument("--project", default=project_id)
    parser.add_argument("--lab", help="Only export questions in this lab directory, e.g. lab01.")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent / "final_submissions.zip")
    args = parser.parse_args()
    db = firestore.Client(project=args.project, database="pytestrunner")
    storage_client = storage.Client(project=args.project)
    try:
        counts = export_archive(
            read_collection(db, "ApiKey"), read_collection(db, "CompletedTask"),
            read_collection(db, "LatestSubmission"), args.output, project=args.project, lab=args.lab,
            storage_client=storage_client)
    finally:
        db.close()
        storage_client.close()
    print(f"Project: {args.project}; lab: {args.lab or 'all'}")
    print(f"Exported {counts[0]} students and {counts[1]} submissions to {args.output}")


if __name__ == "__main__":
    main()
