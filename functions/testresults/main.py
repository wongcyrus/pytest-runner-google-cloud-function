import json
import os
import functions_framework
from google.cloud import datastore
from google.cloud.datastore.query import PropertyFilter


def get_student_id_by_api_key(key: str) -> str:
    client = datastore.Client(project=os.environ.get('GCP_PROJECT'))
    student = client.get(client.key('ApiKey', key))
    return str(student['student_id'])


def load_task(student_id: str) -> list:
    client = datastore.Client(project=os.environ.get('GCP_PROJECT'))
    query = client.query(kind="CompletedTask")
    query.add_filter(filter=PropertyFilter(        
        property_name="student_id",
        operator="=",
        value=student_id))
    results = query.fetch()
    results = list(map(lambda x: x["question"], results))
    results.sort()
    return list(results)

@functions_framework.http
def testresults(request):
    """HTTP Cloud Function.
    Args:
        request (flask.Request): The request object.
        <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`
        <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
    """
    request_args = request.args
    key = request_args["key"]
    print(f"key: {key}")

    student_id = get_student_id_by_api_key(key)
    print(f"student_id: {student_id}")
    completed_tasks = load_task(student_id)   
            
    return json.dumps(completed_tasks),200
