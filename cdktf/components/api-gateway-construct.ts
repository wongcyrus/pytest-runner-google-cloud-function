import { Construct } from "constructs";
import { GoogleApiGatewayGateway } from "../.gen/providers/google-beta/google-api-gateway-gateway";

import { GoogleApiGatewayApi } from "../.gen/providers/google-beta/google-api-gateway-api";
import { GoogleApiGatewayApiConfigA } from "../.gen/providers/google-beta/google-api-gateway-api-config";

import { Fn } from "cdktf";
import { GoogleBetaProvider } from "../.gen/providers/google-beta/provider";
import { GoogleProjectService } from "../.gen/providers/google-beta/google-project-service";
import { GoogleServiceAccount } from "../.gen/providers/google-beta/google-service-account";


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

        const apiConfig = new GoogleApiGatewayApiConfigA(this, "apiConfig", {
            api: apiGatewayApi.apiId,
            openapiDocuments: [
                {
                    document: {
                        path: "spec.yaml",
                        contents: Fn.base64encode(`
swagger: '2.0'
info:
  title: api-gateway
  description: API Gateway
  version: 1.0.0
schemes:
  - https
produces:
  - application/json
paths:
  /pytest:
    get:
      summary: Run PyTest
      operationId: pytest-v1
      security:
        - api_key: []
      x-google-backend:
        address: ${props.url} # You need to change this!
      consumes:
        - application/json
      produces:
        - application/json        
      responses:
        '200':
          description: OK


securityDefinitions:
  api_key:
    type: apiKey
    name: key
    in: query
                        `)
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

    }

    public static async create(scope: Construct, id: string, props: ApigatewayConstructProps) {
        const me = new ApigatewayConstruct(scope, id, props);
        await me.build(props);
        return me;
    }
}