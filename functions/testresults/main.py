import json
import functions_framework
from google.cloud import firestore

def get_student_id_by_api_key(key: str) -> str:
    client = firestore.Client(database="pytestrunner")
    doc_ref = client.collection('ApiKey').document(key)
    doc = doc_ref.get()
    if doc.exists:
        return str(doc.to_dict()['student_id'])
    else:
        raise ValueError("API key not found")

def load_task(student_id: str, is_project: bool) -> list:
    client = firestore.Client(database="pytestrunner")
    query = client.collection('CompletedTask').where('student_id', '==', student_id)
    if is_project:
        query = query.where('is_project', '==', True)
    results = query.stream()
    results = [doc.to_dict()["question"] for doc in results]
    results.sort()
    return results

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

    is_project = "is_project" in request.args

    student_id = get_student_id_by_api_key(key)
    print(f"student_id: {student_id}")
    completed_tasks = load_task(student_id, is_project)   
            
    return json.dumps(completed_tasks),200
