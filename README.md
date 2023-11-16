# pytest-runner-google-cloud-function
Run Pytest with Google Cloud Function

## Deplolyment
Fork this repo and create a Codespace.

### Login your GCP account
```
gcloud auth application-default login
```

### Create GCP resources
```
./deploy.sh 
```
Record down the output api-url, project-id, and service-name.


### Enable the API
Set project
```
gcloud auth login
gcloud config set project <project-id>
gcloud auth application-default set-quota-project <project-id>
gcloud services enable <service-name>
```

## Admin Tools
A set of Python scripts for API key management.

### Before using admin tools

```
gcloud auth login
gcloud config set project <project-id>
gcloud auth application-default set-quota-project <project-id>
```

