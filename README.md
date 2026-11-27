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
- `submission-bucket`: private bucket for immutable student source objects

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

### Export marks and final submitted code

After deploying the updated infrastructure and `pytestrunner` function, each
accepted submission's full UTF-8 code is uploaded before tests to a dedicated
private GCS bucket. Firestore `LatestSubmission` holds its reference and status,
including failed tests and execution errors. `CompletedTask` holds the latest
passing reference and permanently earned mark: a later failure does not remove
a mark, and a later success updates passing code without changing the first
mark's `time`.
Submissions after a previous success are tested again so their latest status is
available. "Final" means the latest received submission per student and question,
not a deadline-based snapshot. A Firestore transaction compares server receipt
timestamps (with submission UUIDs breaking ties) for both latest and latest
passing records. Concurrent older test runs cannot overwrite newer pointers;
an older successful run can still earn a mark. An unfinished run is exported
as `pending`. A retry of the same metadata update cannot regress a terminal
status to pending.

Objects use
`students/<SHA256 student ID>/tasks/<SHA256 question>/submissions/<UUID>.py`.
Uploads require generation-match zero; Firestore stores bucket, object,
generation, SHA-256 and UTF-8 byte size, not full code or service-account keys.
The bucket enforces public-access prevention and uniform bucket IAM. It is
separate from the public report bucket and the one-day function-source bucket,
has no automatic deletion lifecycle, and refuses forced deletion while nonempty.
The runner receives only bucket-scoped `roles/storage.objectCreator` (no source
read, overwrite, list or delete permission). Existing functions share this
service account; splitting their identities is outside this change.

The HTTP request limit is **10 MiB (10,485,760 bytes)** for the entire body or GET
query, including JSON overhead and any supplied project credential; oversize
requests return 413 before upload or testing. Question paths are limited to
1,024 UTF-8 bytes. GCS contains only `sourceCode`, never the separately supplied
`serviceAccountKey`. Credentials embedded by students inside their own source
cannot be detected automatically. Gateway/platform limits may be stricter.

GCS upload failure returns 503 and never runs tests or claims the code was saved.
If upload succeeds but pending metadata fails, 503 identifies the partial save
and tests do not run. If final metadata fails, 503 explicitly leaves the result
and mark unconfirmed; pending metadata may remain. Test execution errors return
500 after saving `error` (or 503 if that update also fails). GCS and Firestore
cannot commit atomically: immutable orphan objects may remain, and there is no
automatic reconciliation/cleanup. A new HTTP retry is a new submission;
internal metadata retries are idempotent. Only a fully recorded passing result
returns success. No historical code migration is performed.

### Updating only the existing test deployment

This implementation does not deploy resources. After reviewing the local
Terraform state and plan, the explicit **test-only** deployment command is:

```bash
PROJECTID=pytest-runner-test-2627 STACK_NAME=pytest-runner-test ./deploy.sh
```

This corresponds to `cdktf/terraform.pytest-runner-test.tfstate`; keep that state
and the existing billing/region/prefix configuration. Do not use the production
`cdktf` stack/state (`pytest-runner-2627`) for this update. Review the plan for
unexpected replacement, especially Firestore, before approval. Existing cloud
IAM, actual upload/download access, gateway limits and runtime behavior still
require a test-deployment smoke test after deployment.

From the repository root, use the admin-tools virtual environment:

```bash
gcloud auth application-default login
admin_tools/venv/bin/python admin_tools/export_final_submissions.py
```

If it does not exist, first run `cd admin_tools && bash setup.sh`.
The project defaults to `admin_tools/config.py`; override it with `--project`.
Use `--output /path/to/export.zip` to choose the destination.
The exporting administrator needs Firestore read access and
`roles/storage.objectViewer` on the private submission bucket (grant only to
authorized administrators; it is not made public by this stack). Admin tools
now require `google-cloud-storage` in addition to Firestore and openpyxl.

There are two deployments: `pytest-runner-2627` and the test deployment
`pytest-runner-test-2627`. The configured default is **not** the test deployment.
To export only **lab01 from the test deployment** to the VM share, run:

```bash
admin_tools/venv/bin/python admin_tools/export_final_submissions.py \
  --project pytest-runner-test-2627 --lab lab01 \
  --output /mnt/hgfs/vmshare/final_submissions_test_lab01.zip
```

For a read-only production export to a **new** archive (no deployment):

```bash
admin_tools/venv/bin/python admin_tools/export_final_submissions.py \
  --project pytest-runner-2627 --lab lab01 \
  --output admin_tools/final_submissions_production_gcs_lab01.zip
```

Choose a new `--output` if retaining previous exports; a successful export
replaces the selected destination. Existing exports are not migrated.

The lab filter applies to both earned marks and source records, matching the
exact lab directory (not `lab010`). Registered students without matching
submissions still appear with zero marks.

The default `admin_tools/final_submissions.zip` contains:
- `scores.xlsx`: student IDs, earned marks, and a 1/0 task matrix.
- `submissions.xlsx`: earned mark, latest pass/fail/error/pending status,
  submission and passing times, completeness, source references and file paths.
- `latest/`: latest submitted UTF-8 source files, without Excel's cell-length limit.
- `passed/`: latest passing UTF-8 source files, independently of latest status.
- `manifest.json`: both source references (including generations), submission
  IDs, first-earned time, and source-file mappings.
- `export_info.json`: the source project, database, lab filter, export time,
  and record counts.

Students registered in `ApiKey` with no submissions still receive a zero-score
row. Task columns include submitted and completed questions; unsubmitted
questions absent from both collections cannot be inferred.
Old completed records without newer latest records are included as `legacy_pass`, with code labeled
`possibly_truncated` unless explicitly known to be complete. Old failed code was
not stored and cannot be recovered. Existing inline `source_code` records in
both collections remain exportable; GCS references take precedence. Downloads
pin the recorded generation and verify SHA-256 when present. A missing or
unreadable object, invalid UTF-8 or checksum mismatch fails the export rather
than silently substituting older code. A partial archive is cleaned up and the
previous destination remains intact on failure. Exports read collections
separately, not as a point-in-time snapshot; export after grading settles when
cross-record consistency is needed.

Exports contain student work and IDs; keep them private. The default ZIP filename
is git-ignored. This script only reads cloud records and writes a local archive.
