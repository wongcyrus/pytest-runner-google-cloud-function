import { Construct } from "constructs";
import { App, TerraformOutput, TerraformStack } from "cdktf";
import { ArchiveProvider } from "./.gen/providers/archive/provider";
import { RandomProvider } from "./.gen/providers/random/provider";
import { DataGoogleBillingAccount } from "./.gen/providers/google-beta/data-google-billing-account";

import { GoogleBetaProvider } from "./.gen/providers/google-beta/provider/index";
import { GoogleProject } from "./.gen/providers/google-beta/google-project";
import { CloudFunctionDeploymentConstruct } from "./components/cloud-function-deployment-construct";
import { CloudFunctionConstruct } from "./components/cloud-function-construct";

import * as dotenv from 'dotenv';
import { ApigatewayConstruct } from "./components/api-gateway-construct";
import { FirestoreConstruct } from "./components/firestore-construct";
import { GoogleProjectIamMember } from "./.gen/providers/google-beta/google-project-iam-member";
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

    // Grant Artifact Registry Reader role to Cloud Functions service agent
    // This must be created AFTER APIs are enabled (so service account exists)
    // but BEFORE Cloud Functions are deployed (so they can use Artifact Registry during build)
    const artifactRegistryIamMember = new GoogleProjectIamMember(this, "cloud-functions-artifact-registry-reader", {
      project: projectId,
      role: "roles/artifactregistry.reader",
      member: `serviceAccount:service-${project.number}@gcf-admin-robot.iam.gserviceaccount.com`,
      dependsOn: cloudFunctionDeploymentConstruct.services,
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
      additionalDependencies: [artifactRegistryIamMember],
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