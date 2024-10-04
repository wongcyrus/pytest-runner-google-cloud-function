import datetime
import json
import os
import subprocess
import zipfile

from os import path
from pathlib import Path
from google.cloud import firestore

import functions_framework

def get_student_id_by_api_key(key: str) -> str:
    db = firestore.Client(database="pytestrunner")
    doc_ref = db.collection('ApiKey').document(key)
    doc = doc_ref.get()
    if doc.exists:
        return str(doc.to_dict()['student_id'])
    else:
        raise ValueError("API key not found")

def save_completed_task(student_id: str, question: str, source_code: str, is_project: bool) -> bool:
    db = firestore.Client(database="pytestrunner")
    doc_ref = db.collection('CompletedTask').document(student_id + "->" + str(question).replace('/', '_'))
    
    data = {
        'student_id': student_id,
        'question': question,
        'source_code': source_code.encode('utf-8')[:1500].decode('utf-8', 'ignore'),
        'is_project': is_project,
        'time': datetime.datetime.now()
    }
    doc_ref.set(data)
    return True


def is_marked(student_id: str, question: str) -> bool:
    db = firestore.Client(database="pytestrunner")
    doc_ref = db.collection('CompletedTask').document(student_id + "->" + str(question).replace('/', '_'))
    doc = doc_ref.get()
    return doc.exists


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
    request_json = request.get_json(silent=True)
    request_args = request.args

    key = request_args["key"]
    print(f"key: {key}")

    student_id = get_student_id_by_api_key(key)
    print(f"student_id: {student_id}")

    service_account_key = None
    if request.method == "GET":
        source_code_file_path = request_args["sourceCodeFilePath"]
        source_code = request_args["sourceCode"] if "is_project" in request.args else None
        service_account_key = request_args["serviceAccountKey"]
        assignment_id = request_args["assignmentId"]
    else:
        source_code_file_path = request_json["sourceCodeFilePath"]
        source_code = request_json["sourceCode"]
        service_account_key = request_json.get("serviceAccountKey")
        assignment_id = request_json.get("assignmentId")

    if not source_code or not source_code_file_path:
        return '{ "error": "source_code and source_code_file_path must present." }', 422

    print(f"source_code_file_path: {source_code_file_path}")
    # print(f"source_code: \n{source_code}")

    question = source_code_file_path

    if is_marked(student_id, question):
        return 'Repeated Successful Test.', 200

    root = path.dirname(path.abspath(__file__))

    source = (assignment_id + '.zip') if assignment_id is not None else "assignments.zip"

    zipped_pytest_code = path.join(path.dirname(
        path.realpath(__file__)), source if service_account_key is None else "project.zip")
    print(f"zipped_pytest_code: {zipped_pytest_code}")
    with zipfile.ZipFile(zipped_pytest_code) as file:
        file.extractall(path=root)
    print(f"Extracted zip file to {root}")

    code_file_path = path.join(root, source_code_file_path)
    with open(code_file_path, 'w') as filetowrite:
        filetowrite.write(source_code)

    # text = Path(code_file_path).read_text()
    # print(text)

    if service_account_key is not None:
        service_account_key_path = path.join(root, "service_account_key.json")
        with open(service_account_key_path, 'w') as filetowrite:
            filetowrite.write(service_account_key)
        print("Saved:" + service_account_key_path)


    # Source lab\lab01\ch01_t01_hello_world.py to Test tests\lab01\test_ch01_t01_hello_world.py
    source_code_file_path_segments = source_code_file_path.split("/")
    test_code_file_path = path.join(
        root, "tests", source_code_file_path_segments[1], "test_"+source_code_file_path_segments[2])

    test_result_text = os.path.join(root, 'result.json')

    cmd = f"""PREFIX=gcf STUDENT_ID={student_id} python -m pytest -v {test_code_file_path} --json-report --json-report-file={test_result_text}"""
    print(cmd)
    test_result = subprocess.getoutput(cmd)
    print(test_result)
    test_result_text = Path(test_result_text).read_text()
    print(test_result_text)

    try:
        test_result_json = json.loads(test_result_text)
        is_all_tests_passed = test_result_json["summary"]["passed"] / \
            test_result_json["summary"]["total"] == 1
        print(f"is_all_tests_passed: {is_all_tests_passed}")

        if is_all_tests_passed:
            save_completed_task(student_id, question, source_code, service_account_key is not None)
            return "Test Success and saved the result.", 200

    except BaseException as ex:
        print(f"Unexpected {ex=}, {type(ex)=}")

    return test_result_text