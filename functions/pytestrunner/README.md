# Python Assignment exercises

The deployed runner requires `SUBMISSION_BUCKET`, provisioned by the CDKTF
private submission-bucket construct. Accepted source is uploaded before tests;
Firestore stores generation-pinned latest and latest-passing references and
retains earned marks. The whole HTTP request is limited to 10 MiB; source is
never truncated or stored inline in new Firestore records. See the root README
for storage-failure semantics, administrator access and export commands.

Login your Google Cloud Console, open Cloud Shall and run the following commands to enable API.
```
gcloud services enable vision.googleapis.com
gcloud services enable translate.googleapis.com
gcloud services enable language.googleapis.com
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
```

## Windows
### Change Powershell execution policy

Demo of setting up the Execution Policy.
https://youtu.be/R11kUjafVEo?list=PLtgJR0xD2TPdBfg5oIKseNuN0tX_DgPkH&t=1738

Open a Powershell window as administrator and type the following:
```Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser```
Then respond y to any questions.

You need to use create virtual environment as you should not corrupt your Python in Windows.
```
python -m venv .venv
.venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

## Codespace
It is fine to use the Linus Python interpreter directly, as you can delete Codepace and create new one if there is any problem easily.
```
pip install -r requirements.txt
```

![Open in Codespaces](https://classroom.github.com/assets/open-in-codespaces-abfff4d4e15f9e1bd8274d9a39a0befe03a0632bb0f153d0ec72ff541cedbe34.svg)
