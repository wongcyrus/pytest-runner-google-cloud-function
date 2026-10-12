import { Construct } from "constructs";
import { App, TerraformOutput, TerraformStack } from "cdktn";
import { ArchiveProvider } from "./.gen/providers/archive/provider";
import { RandomProvider } from "./.gen/providers/random/provider";
import { DataGoogleBillingAccount } from "./.gen/providers/google-beta/data-google-billing-account";

import { GoogleBetaProvider } from "./.gen/providers/google-beta/provider/index";
import { GoogleProject } from "./.gen/providers/google-beta/google-project";
import { CloudFunctionDeploymentConstruct } from "./components/cloud-function-deployment-construct";
import { CloudFunctionConstruct } from "./components/cloud-function-construct";

import * as fs from 'fs';
import * as path from 'path';
import * as dotenv from 'dotenv';
import { ApigatewayConstruct } from "./components/api-gateway-construct";
import { FirestoreConstruct } from "./components/firestore-construct";
import { WebsiteBucketConstruct } from "./components/website-bucket-construct";
import { DailySchedulerConstruct } from "./components/scheduler-construct";
import { GoogleProjectIamMember } from "./.gen/providers/google-beta/google-project-iam-member";
import { GoogleProjectServiceIdentity } from "./.gen/providers/google-beta/google-project-service-identity";
dotenv.config();

class PyTestRunnerStack extends TerraformStack {
  constructor(scope: Construct, id: string) {
    super(scope, id);

    // define resources here
  }
  async buildGcpLabEngineStack() {
    const projectId = process.env.PROJECTID!;

    const googleBetaProvider = new GoogleBetaProvider(this, "google", {
      region: process.env.REGION!,
    });
    const archiveProvider = new ArchiveProvider(this, "archive", {});
    const randomProvider = new RandomProvider(this, "random", {});

    const billingAccount = new DataGoogleBillingAccount(this, "billing-account", {
      billingAccount: process.env.BillING_ACCOUNT!,
    });

    const project = new GoogleProject(this, "project", {
      projectId: projectId,
      name: projectId,
      billingAccount: billingAccount.id,
      deletionPolicy: "DELETE",
    });

    const cloudFunctionDeploymentConstruct =
      new CloudFunctionDeploymentConstruct(this, "cloud-function-deployment", {
        project: project.projectId,
        region: process.env.REGION!,
        archiveProvider: archiveProvider,
        randomProvider: randomProvider,
      });

    // Synchronously request GCP to create Cloud Functions and Cloud Build managed service identities
    const gcfServiceIdentity = new GoogleProjectServiceIdentity(this, "gcf-service-identity", {
      project: projectId,
      service: "cloudfunctions.googleapis.com",
      provider: googleBetaProvider,
      dependsOn: cloudFunctionDeploymentConstruct.services,
    });

    const cloudBuildServiceIdentity = new GoogleProjectServiceIdentity(this, "cloudbuild-service-identity", {
      project: projectId,
      service: "cloudbuild.googleapis.com",
      provider: googleBetaProvider,
      dependsOn: cloudFunctionDeploymentConstruct.services,
    });

    // Grant Artifact Registry Reader role to Cloud Functions service agent
    // Using gcfServiceIdentity guarantees the service account is created by GCP before assigning the role
    const artifactRegistryIamMember = new GoogleProjectIamMember(this, "cloud-functions-artifact-registry-reader", {
      project: projectId,
      role: "roles/artifactregistry.reader",
      member: gcfServiceIdentity.member,
      provider: googleBetaProvider,
      dependsOn: [gcfServiceIdentity, cloudBuildServiceIdentity],
    });

    //For the first deployment, it takes a while for API to be enabled.
    // await new Promise(r => setTimeout(r, 30000));

    const pytestrunnerCloudFunctionConstruct = await CloudFunctionConstruct.create(this, "pytestrunnerCloudFunctionConstruct", {
      functionName: "pytestrunner",
      runtime: "python311",
      entryPoint: "pytestrunner",
      timeout: 600,
      availableMemory: "512Mi",
      makePublic: false,
      cloudFunctionDeploymentConstruct: cloudFunctionDeploymentConstruct,      
      environmentVariables: {      
        "PREFIX": process.env.PREFIX!,      
      },
      additionalDependencies: [artifactRegistryIamMember],
    });

    await FirestoreConstruct.create(this, " pytestrunnerDatastore", {
      project: project.projectId,
      servicesAccount: pytestrunnerCloudFunctionConstruct.serviceAccount,
    });

    const testResultsCloudFunctionConstruct = await CloudFunctionConstruct.create(this, "testResultsCloudFunctionConstruct", {
      functionName: "testresults",
      runtime: "python311",
      entryPoint: "testresults",
      timeout: 600,
      availableMemory: "512Mi",
      makePublic: false,
      cloudFunctionDeploymentConstruct: cloudFunctionDeploymentConstruct,
      serviceAccount: pytestrunnerCloudFunctionConstruct.serviceAccount,
      additionalDependencies: [artifactRegistryIamMember, pytestrunnerCloudFunctionConstruct.cloudFunction],
    });

    const websiteBucketConstruct = new WebsiteBucketConstruct(this, "websiteBucketConstruct", {
      project: project.projectId,
      region: process.env.REGION!,
      functionServiceAccount: pytestrunnerCloudFunctionConstruct.serviceAccount,
      dependsOn: cloudFunctionDeploymentConstruct.services,
    });

    // Automatically sync Namelist.xlsx from admin_tools to functions/scorereport before packaging
    const namelistSource = path.resolve(__dirname, "..", "admin_tools", "Namelist.xlsx");
    const namelistDestDir = path.resolve(__dirname, "..", "functions", "scorereport");
    const namelistDest = path.join(namelistDestDir, "Namelist.xlsx");
    if (fs.existsSync(namelistSource)) {
      fs.mkdirSync(namelistDestDir, { recursive: true });
      fs.copyFileSync(namelistSource, namelistDest);
      console.log(`[CDKTF] Synced Namelist.xlsx from admin_tools to functions/scorereport`);
    } else {
      console.warn(`[CDKTF] Warning: ${namelistSource} not found. Ensure Namelist.xlsx is present in admin_tools.`);
    }

    const scoreReportCloudFunctionConstruct = await CloudFunctionConstruct.create(this, "scoreReportCloudFunctionConstruct", {
      functionName: "scorereport",
      runtime: "python311",
      entryPoint: "scorereport",
      timeout: 600,
      availableMemory: "512Mi",
      makePublic: false,
      cloudFunctionDeploymentConstruct: cloudFunctionDeploymentConstruct,
      serviceAccount: pytestrunnerCloudFunctionConstruct.serviceAccount,
      environmentVariables: {
        "REPORT_BUCKET": websiteBucketConstruct.bucket.name,
      },
      additionalDependencies: [artifactRegistryIamMember, websiteBucketConstruct.bucket],
    });

    new DailySchedulerConstruct(this, "dailyScoreReportScheduler", {
      name: "daily-score-report-job",
      project: project.projectId,
      region: process.env.REGION!,
      schedule: "0 0 * * *",
      targetUri: scoreReportCloudFunctionConstruct.cloudFunction.url,
      serviceAccount: pytestrunnerCloudFunctionConstruct.serviceAccount,
      dependsOn: [scoreReportCloudFunctionConstruct.cloudFunction],
    });

    const apigatewayConstruct = await ApigatewayConstruct.create(this, "api-gateway", {
      api: "pytestrunnerapi",
      project: project.projectId,
      provider: googleBetaProvider,
      replaces: { "GRADER": pytestrunnerCloudFunctionConstruct.cloudFunction.url, "TEST_RESULTS": testResultsCloudFunctionConstruct.cloudFunction.url },
      servicesAccount: pytestrunnerCloudFunctionConstruct.serviceAccount,
    });

    new TerraformOutput(this, "project-id", {
      value: project.projectId,
    });

    new TerraformOutput(this, "api-url", {
      value: apigatewayConstruct.gateway.defaultHostname,
    });

    new TerraformOutput(this, "service-name", {
      value: apigatewayConstruct.apiGatewayApi.managedService,
    });

    new TerraformOutput(this, "report-website-url", {
      value: `https://storage.googleapis.com/${websiteBucketConstruct.bucket.name}/index.html`,
    });

    new TerraformOutput(this, "report-function-url", {
      value: scoreReportCloudFunctionConstruct.cloudFunction.url,
    });

  }
}

async function buildStack(scope: Construct, id: string) {
  const stack = new PyTestRunnerStack(scope, id);
  await stack.buildGcpLabEngineStack();
}

async function createApp(): Promise<App> {
  const app = new App();
  await buildStack(app, "cdktf");
  return app;
}

createApp().then((app) => app.synth());