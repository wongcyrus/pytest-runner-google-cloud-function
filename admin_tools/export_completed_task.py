from google.cloud import firestore
from config import project_id
import os

def get_all_api_completed_task():
    client = firestore.Client(project=project_id,database="pytestrunner")
    collection_ref = client.collection("CompletedTask")
    query = collection_ref.order_by("student_id")
    results = [dict(doc.to_dict(), key=doc.id) for doc in query.stream()]       
    return results

def save_api_tasks_to_xlsx(api_keys):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["id","question","time"])
    for key in api_keys:
        print(key)       
        time = key["time"].replace(tzinfo=None)
        ws.append([key["student_id"],key["question"],time])
    # save to current python directory
    current_directory = os.path.dirname(os.path.realpath(__file__))
    wb.save(os.path.join(current_directory, "tasks.xlsx"))  


if __name__ == "__main__":
    completed_tasks = get_all_api_completed_task()
    # print(len(completed_tasks))
    save_api_tasks_to_xlsx(completed_tasks)