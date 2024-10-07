from google.cloud import firestore
from config import project_id
import os
from openpyxl import Workbook

def get_all_api_keys():
    db = firestore.Client(project=project_id,database="pytestrunner")
    api_keys_ref = db.collection("ApiKey")
    api_keys = api_keys_ref.order_by("student_id").stream()
    results = [api_key.to_dict() for api_key in api_keys]
    
    return results

def completed_task(student_id: str) -> list:
    db = firestore.Client(project=project_id,database="pytestrunner")
    completed_tasks_ref = db.collection("CompletedTask")
    query = completed_tasks_ref.where("student_id", "==", str(student_id))
    results = query.stream()
    results = [task.to_dict()["question"] for task in results]
    results.sort()
    print(f"Student {student_id} has completed {len(results)} tasks.")
    return results

def save_to_xlsx(student_task:dict, all_tasks:list):    
    wb = Workbook()
    ws = wb.active
    header = ["id","score"]
    # remove the first 4 characters "task" from all_tasks
    header.extend(list(map(lambda x: x[4:], all_tasks)))
    ws.append(header)

    #Loop through student_task with for loop sort by key
    for key, value in sorted(student_task.items(), key=lambda item: str(item[0])):
        row = [key,len(value)]
        for task in all_tasks:
            if task in value:
                row.append("1")
            else:
                row.append("0")
        ws.append(row)
    current_directory = os.path.dirname(os.path.realpath(__file__))
    wb.save(os.path.join(current_directory, "scores.xlsx"))  


if __name__ == "__main__":
    api_keys = get_all_api_keys()
    # api_keys = api_keys[:10]
    
    # extract student_id from api_keys
    print("Get Student Records.")
    student_ids = list(map(lambda x: {"id":x["student_id"],"tasks":completed_task(x["student_id"])}, api_keys))
    # Combine list of dict into one dict
    student_task = {d['id']: d['tasks'] for d in student_ids} 
    # Join all tasks into a set
    all_tasks = set().union(*student_task.values())
    # convert all_tasks to list and sort it 
    all_tasks = list(all_tasks)
    all_tasks.sort()
    print("Save to xlsx.")
    save_to_xlsx(student_task,all_tasks)    
    print("Done.")
    