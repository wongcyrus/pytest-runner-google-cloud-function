import { Construct } from "constructs";
import { hashElement } from 'folder-hash';
import { DataArchiveFile } from "../.gen/providers/archive/data-archive-file";
import { CloudRunServiceIamBinding } from "../.gen/providers/google/cloud-run-service-iam-binding";
import { Cloudfunctions2Function, Cloudfunctions2FunctionEventTrigger } from "../.gen/providers/google/cloudfunctions2-function";
import { Cloudfunctions2FunctionIamBinding } from "../.gen/providers/google/cloudfunctions2-function-iam-binding";
import { ServiceAccount } from "../.gen/providers/google/service-account";
import { StorageBucketObject } from "../.gen/providers/google/storage-bucket-object";
import { CloudFunctionDeploymentConstruct } from "./cloud-function-deployment-construct";
import path = require("path");

export interface CloudFunctionConstructProps {
    readonly functionName: string;
    readonly functionCode?: string;
    readonly runtime: string;
    readonly entryPoint: string;
    readonly availableMemory?: string;
    readonly timeout?: number;
    readonly cloudFunctionDeploymentConstruct: CloudFunctionDeploymentConstruct;
    readonly environmentVariables?: { [key: string]: string };
    readonly eventTrigger?: Cloudfunctions2FunctionEventTrigger;
    readonly makePublic?: boolean;
}

export class CloudFunctionConstruct extends Construct {
    public cloudFunction!: Cloudfunctions2Function;
    public serviceAccount: ServiceAccount;
    private props: CloudFunctionConstructProps;
    public project: string;

    private constructor(scope: Construct, id: string, props: CloudFunctionConstructProps) {
        super(scope, id);
        let accountId = props.functionName + props.entryPoint.replace(/[^a-z0-9]/gi, '');
        accountId = accountId.substring(0, 27).toLowerCase();
        this.serviceAccount = new ServiceAccount(this, "service-account", {
            accountId: accountId,
            project: props.cloudFunctionDeploymentConstruct.project,
            displayName: props.functionName + props.entryPoint ?? "",
        });
        this.props = props;
        this.project = props.cloudFunctionDeploymentConstruct.project;
    }

    private async build(props: CloudFunctionConstructProps) {

        const options = {
            folders: { exclude: ['.*', 'node_modules', 'test_coverage', "bin", "obj"] },
            files: { include: ['*.js', '*.json', '*.cs', ".csproject"] },
        };
        const hash = await hashElement(path.resolve(__dirname, "..", "..", "functions", this.props.functionCode ?? this.props.functionName), options);
        const outputFileName = `function-source-${hash.hash}.zip`;
        const code = new DataArchiveFile(this, "archiveFile", {
            type: "zip",
            sourceDir: path.resolve(__dirname, "..", "..", "functions", this.props.functionCode ?? this.props.functionName),
            outputPath: path.resolve(__dirname, "..", "cdktf.out", "functions", outputFileName)
        });

        const storageBucketObject = new StorageBucketObject(this, "storage-bucket-object", {
            name: outputFileName,
            bucket: this.props.cloudFunctionDeploymentConstruct.sourceBucket.name,
            source: code.outputPath,
        });


        this.cloudFunction = new Cloudfunctions2Function(this, "cloud-function", {
            name: this.props.functionName.toLowerCase(),
            project: this.props.cloudFunctionDeploymentConstruct.project,
            location: this.props.cloudFunctionDeploymentConstruct.region,
            buildConfig: {
                runtime: props.runtime,
                entryPoint: this.props.entryPoint ?? this.props.functionName,
                source: {
                    storageSource: {
                        bucket: this.props.cloudFunctionDeploymentConstruct.sourceBucket.name,
                        object: storageBucketObject.name,
                    }
                }
            },
            serviceConfig: {
                maxInstanceCount: 1,
                availableMemory: props.availableMemory ?? "128Mi",
                timeoutSeconds: props.timeout ?? 60,
                serviceAccountEmail: this.serviceAccount.email,
                environmentVariables: props.environmentVariables ?? {},
            },
            eventTrigger: props.eventTrigger,
        });

        const member = props.makePublic ?? false ? "allUsers" : "serviceAccount:" + this.serviceAccount.email;
        new Cloudfunctions2FunctionIamBinding(this, "cloudfunctions2-function-iam-member", {
            project: this.cloudFunction.project,
            location: this.cloudFunction.location,
            cloudFunction: this.cloudFunction.name,
            role: "roles/cloudfunctions.invoker",
            members: [member]
        });

        new CloudRunServiceIamBinding(this, "cloud-run-service-iam-binding", {
            project: this.props.cloudFunctionDeploymentConstruct.project,
            location: this.cloudFunction.location,
            service: this.cloudFunction.name,
            role: "roles/run.invoker",
            members: [member]
        });
    }

    public static async create(scope: Construct, id: string, props: CloudFunctionConstructProps) {
        const me = new CloudFunctionConstruct(scope, id, props);
        await me.build(props);
        return me;
    }
}