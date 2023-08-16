import { Construct } from "constructs";
import { GoogleApiGatewayGateway } from "../.gen/providers/google-beta/google-api-gateway-gateway";

import { GoogleApiGatewayApi } from "../.gen/providers/google-beta/google-api-gateway-api";
import { GoogleApiGatewayApiConfigA } from "../.gen/providers/google-beta/google-api-gateway-api-config";

import { Fn } from "cdktf";
import { GoogleBetaProvider } from "../.gen/providers/google-beta/provider";
import { GoogleProjectService } from "../.gen/providers/google-beta/google-project-service";
import { GoogleServiceAccount } from "../.gen/providers/google-beta/google-service-account";

import path = require("path");
import fs = require("fs");


export interface ApigatewayConstructProps {
    readonly api: string;
    readonly url: string;
    readonly project: string;
    readonly provider: GoogleBetaProvider;
    readonly servicesAccount: GoogleServiceAccount;
}

export class ApigatewayConstruct extends Construct {
    public readonly apis = [
        "iam.googleapis.com",
        "apigateway.googleapis.com",
        "servicemanagement.googleapis.com",
        "servicecontrol.googleapis.com",
    ];
    prop: ApigatewayConstructProps;

    public gateway!: GoogleApiGatewayGateway;

    private constructor(scope: Construct, id: string, props: ApigatewayConstructProps) {
        super(scope, id);
        this.prop = props;
    }

    private async build(props: ApigatewayConstructProps) {

        const services = [];
        for (const api of this.apis) {
            services.push(new GoogleProjectService(this, `${api.replaceAll(".", "")}`, {
                project: props.project,
                service: api,
                disableOnDestroy: false,
            }));
        }
        const apiGatewayApi = new GoogleApiGatewayApi(this, "api", {
            apiId: props.api,
            project: props.project,
            provider: props.provider,
            dependsOn: services,
        });

        ;

        const apiConfig = new GoogleApiGatewayApiConfigA(this, "apiConfig", {
            api: apiGatewayApi.apiId,
            openapiDocuments: [
                {
                    document: {
                        path: "spec.yaml",
                        contents: Fn.base64encode(fs.readFileSync(path.resolve(__dirname, "spec.yaml"), "utf8").replace("{{URL}}", props.url)),
                    }
                },
            ],
            gatewayConfig: {
                backendConfig: {
                    googleServiceAccount: props.servicesAccount.email,
                }
            },
            lifecycle: {
                createBeforeDestroy: true,
            },
            project: props.project,
            provider: props.provider,
            dependsOn: services,
        })

        this.gateway = new GoogleApiGatewayGateway(this, "gateway", {
            gatewayId: "gateway",
            apiConfig: apiConfig.id,
            project: props.project,
            provider: props.provider,
            dependsOn: services,
        });

        new GoogleProjectService(this, `GatewayService`, {
            project: props.project,
            service: this.gateway.,
            disableOnDestroy: false,
        })

    }

    public static async create(scope: Construct, id: string, props: ApigatewayConstructProps) {
        const me = new ApigatewayConstruct(scope, id, props);
        await me.build(props);
        return me;
    }
}