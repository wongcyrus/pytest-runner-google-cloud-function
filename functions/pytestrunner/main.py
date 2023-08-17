import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from flask import escape

import functions_framework
from google.cloud import datastore

datastore_client = datastore.Client()

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

    student_id = lookup_api_key(key)
    print(f"student_id: {student_id}")

    if request.method == "GET":
        source_code_file_path = request_args["sourceCodeFilePath"]
        source_code = request_args["sourceCode"]
    else:
        source_code_file_path = request_json["sourceCodeFilePath"]
        source_code = request_json["sourceCode"]

    if not source_code or not source_code_file_path:
        return '{ "error": "source_code and source_code_file_path must present." }', 422
    
    print(f"source_code_file_path: {source_code_file_path}")
    print(f"source_code: \n{source_code}")
    
    with tempfile.TemporaryDirectory() as tmpdirname:
        print(f"Created temporary directory: {tmpdirname}")
        zipped_pyTest_code = os.path.join(os.path.dirname(
        os.path.realpath(__file__)), 'assignments.zip')
        file = zipfile.ZipFile(zipped_pyTest_code)
        file.extractall(path=tmpdirname)   
        print(f"Extracted zip file to {tmpdirname}")

        assignment_path = os.path.join(tmpdirname, "assignments")
        code_file_path = os.path.join(tmpdirname, "assignments", source_code_file_path)
        with open(code_file_path, 'w') as filetowrite:
            filetowrite.write(source_code)

        text = Path(code_file_path).read_text()
        print(text)

        # Source lab\lab01\ch01_t01_hello_world.py to Test tests\lab01\test_ch01_t01_hello_world.py
        source_code_file_path_segments = source_code_file_path.split("/")
        test_code_file_path = os.path.join(
            tmpdirname, "assignments", "tests", source_code_file_path_segments[1], "test_"+source_code_file_path_segments[2])
        
        virtual_env_path = os.path.join(tmpdirname, "assignments", ".venv")
        activate_virtual_env_path = os.path.join(
            tmpdirname, "assignments", ".venv", "bin", "activate")
        pip_virtual_env_path = os.path.join(
            tmpdirname, "assignments", ".venv", "bin", "pip")
        os.chdir(assignment_path)
        test_result = subprocess.getoutput(
            f'python -m venv {virtual_env_path}')
        print(test_result)
        test_result = subprocess.getoutput(
            f'{pip_virtual_env_path} install -r requirements.txt')
        print(test_result)

        test_result_text = os.path.join(tmpdirname, 'result.json')
      
        cmd = f""". {activate_virtual_env_path}
python -m pytest -v {test_code_file_path} --json-report --json-report-file={test_result_text}
"""
        print(cmd)
        test_result = subprocess.getoutput(cmd)
        print(test_result)
        test_result_text = Path(test_result_text).read_text()
        print(test_result_text)
        shutil.rmtree(tmpdirname)

    return test_result_text
