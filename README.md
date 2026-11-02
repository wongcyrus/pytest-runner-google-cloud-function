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
Copy `cdktf/.env.template` to `cdktf/.env` and configure the project ID, billing account, region, and prefix.
`STACK_NAME` is optional and defaults to `cdktf`, preserving the existing stack identity and local state file.

```bash
./deploy.sh 
```

For a separate deployment, use both a new, globally unique project ID and a distinct stack name:

```bash
PROJECTID=my-pytest-runner-dev STACK_NAME=pytest-runner-dev ./deploy.sh
```

Keep the original project ID, stack name, and local Terraform state when updating an existing deployment.
Changing only the project ID while reusing a stack's state can propose replacing existing resources.
Changing the stack name does not migrate its state. Local state files are not committed to this repository.

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

### Known first-deployment limitation

Firestore database creation can succeed while the provider's immediate metadata read returns a 403, leaving the database tainted in Terraform state.
This is tracked in [hashicorp/terraform-provider-google#30496](https://github.com/hashicorp/terraform-provider-google/issues/30496).
Inspect the existing database and Terraform plan before retrying; do not blindly approve database replacement.
The function deployment-order fix prevents concurrent source-bucket initialization but does not resolve this separate Firestore failure.

## Admin Tools
A set of Python scripts for API key management and report generation.

### Before using admin tools

```bash
gcloud auth login
gcloud config set project <project-id>
gcloud auth application-default set-quota-project <project-id>
```
