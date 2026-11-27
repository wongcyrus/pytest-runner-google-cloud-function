import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
import uuid

from os import path
from pathlib import Path
from google.cloud import firestore, storage

import functions_framework

MAX_REQUEST_BYTES = 10 * 1024 * 1024


def get_student_id_by_api_key(key: str) -> str:
    db = firestore.Client(database="pytestrunner")
    doc_ref = db.collection('ApiKey').document(key)
    doc = doc_ref.get()
    if doc.exists:
        return str(doc.to_dict()['student_id'])
    else:
        raise ValueError("API key not found")


def upload_submission(student_id, question, source_code, submission_id):
    code = source_code.encode("utf-8")
    student = hashlib.sha256(student_id.encode("utf-8")).hexdigest()
    task = hashlib.sha256(question.encode("utf-8")).hexdigest()
    object_name = f"students/{student}/tasks/{task}/submissions/{submission_id}.py"
    client = storage.Client()
    try:
        blob = client.bucket(os.environ["SUBMISSION_BUCKET"]).blob(object_name)
        blob.upload_from_string(
            code, content_type="text/plain; charset=utf-8", if_generation_match=0)
        return {
            "bucket": blob.bucket.name,
            "object": object_name,
            "generation": str(blob.generation),
            "sha256": hashlib.sha256(code).hexdigest(),
            "size_bytes": len(code),
        }
    finally:
        client.close()


def submission_order(record):
    timestamp = record.get("submitted_at", record.get("time"))
    if timestamp is None:
        timestamp = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    elif timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
    return timestamp, record.get("submission_id", "")


def save_submission(student_id, question, source_ref, is_project,
                    submitted_at, submission_id, status, summary=None):
    db = firestore.Client(database="pytestrunner")
    try:
        document_id = student_id + "->" + question.replace("/", "_")
        latest_ref = db.collection("LatestSubmission").document(document_id)
        completed_ref = db.collection("CompletedTask").document(document_id)
        data = {
            "student_id": student_id,
            "question": question,
            "source_ref": source_ref,
            "source_code_complete": True,
            "is_project": is_project,
            "time": submitted_at,
            "submitted_at": submitted_at,
            "submission_id": submission_id,
            "status": status,
            "summary": summary or {},
        }

        @firestore.transactional
        def save(transaction):
            latest = latest_ref.get(transaction=transaction)
            completed = completed_ref.get(transaction=transaction) if status == "pass" else None
            previous = latest.to_dict() if latest.exists else {}
            order = submission_order(data)
            if not latest.exists or order > submission_order(previous) or (
                    order == submission_order(previous) and previous.get("status") == "pending"):
                transaction.set(latest_ref, data)
            # Older successful runs can still earn a mark, but never replace newer passing code.
            if completed is not None and (
                    not completed.exists or order > submission_order(completed.to_dict())):
                passing = dict(data)
                if completed.exists:
                    passing["time"] = completed.to_dict().get("time", submitted_at)
                transaction.set(completed_ref, passing)

        save(db.transaction())
    finally:
        db.close()


def run_tests(source_code_file_path, source_code, service_account_key, assignment_id, student_id):
    bundle_root = path.dirname(path.abspath(__file__))
    source = assignment_id + ".zip" if assignment_id is not None else "assignments.zip"
    zipped_pytest_code = path.join(
        bundle_root, source if service_account_key is None else "project.zip")
    with tempfile.TemporaryDirectory() as root:
        with zipfile.ZipFile(zipped_pytest_code) as file:
            file.extractall(path=root)
        code_file_path = path.join(root, source_code_file_path)
        Path(code_file_path).write_text(source_code, encoding="utf-8")
        if service_account_key is not None:
            Path(root, "service_account_key.json").write_text(
                service_account_key, encoding="utf-8")
        segments = source_code_file_path.split("/")
        test_code_file_path = path.join(root, "tests", segments[1], "test_" + segments[2])
        report_path = path.join(root, "result.json")
        env = dict(os.environ, PREFIX=os.environ.get("PREFIX", ""), STUDENT_ID=student_id)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", test_code_file_path,
             "--json-report", "--json-report-file=" + report_path],
            cwd=root, env=env, capture_output=True, text=True)
        report_text = Path(report_path).read_text(encoding="utf-8")
        report = json.loads(report_text)
        summary = report.get("summary", {})
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)
        status = "pass" if result.returncode == 0 and total > 0 and passed == total else "fail"
        if result.returncode not in (0, 1):
            status = "error"
        return report_text, status, summary


@functions_framework.http
def pytestrunner(request):
    """HTTP Cloud Function.
    Args:
        request (flask.Request): The request object.
        <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`
        <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
    """
    if (request.content_length is not None and request.content_length > MAX_REQUEST_BYTES
            or len(request.get_data()) > MAX_REQUEST_BYTES
            or len(request.query_string) > MAX_REQUEST_BYTES):
        return '{"error": "Request exceeds the 10 MiB limit."}', 413
    submitted_at = datetime.datetime.now(datetime.timezone.utc)
    submission_id = uuid.uuid4().hex
    request_json = request.get_json(silent=True) or {}
    request_args = request.args

    key = request_args["key"]
    student_id = get_student_id_by_api_key(key)
    print(f"student_id: {student_id}")

    service_account_key = None
    if request.method == "GET":
        source_code_file_path = request_args.get("sourceCodeFilePath")
        source_code = request_args.get("sourceCode") if "is_project" in request.args else None
        service_account_key = request_args.get("serviceAccountKey")
        assignment_id = request_args.get("assignmentId")
    else:
        source_code_file_path = request_json.get("sourceCodeFilePath")
        source_code = request_json.get("sourceCode")
        service_account_key = request_json.get("serviceAccountKey")
        assignment_id = request_json.get("assignmentId")

    if (not isinstance(source_code, str) or not isinstance(source_code_file_path, str)
            or not source_code_file_path or len(source_code_file_path.encode("utf-8")) > 1024):
        return '{ "error": "source_code and source_code_file_path must present." }', 422
    if len(source_code.encode("utf-8")) > MAX_REQUEST_BYTES:
        return '{"error": "Request exceeds the 10 MiB limit."}', 413

    print(f"source_code_file_path: {source_code_file_path}")
    # print(f"source_code: \n{source_code}")

    question = source_code_file_path

    try:
        source_ref = upload_submission(student_id, question, source_code, submission_id)
    except Exception:
        return '{"error": "Source storage failed; submission was not accepted or tested."}', 503

    def save(status, summary=None):
        save_submission(student_id, question, source_ref, service_account_key is not None,
                        submitted_at, submission_id, status, summary)

    try:
        save("pending")
    except Exception:
        return ('{"error": "Source uploaded, but submission metadata failed; '
                'submission was not accepted or tested."}', 503)
    try:
        test_result_text, status, summary = run_tests(
            source_code_file_path, source_code, service_account_key, assignment_id, student_id)
    except Exception:
        try:
            save("error")
        except Exception:
            return ('{"error": "Test execution and metadata update failed; '
                    'source uploaded, submission metadata may remain pending."}', 503)
        return '{"error": "Test execution failed; submission code was saved."}', 500

    try:
        save(status, summary)
    except Exception:
        return ('{"error": "Source uploaded, but result metadata failed; '
                'submission metadata may remain pending and mark was not confirmed."}', 503)
    if status == "pass":
        return "Test Success and saved the result.", 200
    return test_result_text
