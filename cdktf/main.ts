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
import { DatastoreConstruct } from "./components/datastore-construct";
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
      skipDelete: false
    });

    const cloudFunctionDeploymentConstruct =
      new CloudFunctionDeploymentConstruct(this, "cloud-function-deployment", {
        project: project.projectId,
        region: process.env.REGION!,
        archiveProvider: archiveProvider,
        randomProvider: randomProvider,
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
    });

    await DatastoreConstruct.create(this, " pytestrunnerDatastore", {
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