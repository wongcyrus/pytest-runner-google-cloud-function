# pytest-runner-google-cloud-function
Run Pytest with Google Cloud Function

## Deployment
Fork this repo and create a Codespace.

### 1. Login your GCP account
```bash
gcloud auth application-default login
```

### 2. Provide Student Namelist
Place your student list in `admin_tools/Namelist.xlsx` (you can use `admin_tools/Namelist_template.xlsx` as a template).
- The Excel sheet should contain columns: `Student No` and `Student Name`.
- `admin_tools/Namelist.xlsx` is git-ignored and will **not** be committed to GitHub.
- CDKTF will automatically sync and package this file into the `scorereport` Cloud Function bundle during deployment.

### 3. Create GCP resources
```bash
./deploy.sh 
```
Record down the output values:
- `api-url`: API Gateway domain
- `project-id`: Google Cloud Project ID
- `service-name`: Managed API service name
- `report-website-url`: Static website URL hosting the student score report
- `report-function-url`: Score report Cloud Function endpoint

### 4. Enable the API
Set project:
```bash
gcloud auth login
gcloud config set project <project-id>
gcloud auth application-default set-quota-project <project-id>
gcloud services enable <service-name>
```

## Admin Tools
A set of Python scripts for API key management and report generation.

### Before using admin tools

```bash
gcloud auth login
gcloud config set project <project-id>
gcloud auth application-default set-quota-project <project-id>
```
