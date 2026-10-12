import { Construct } from "constructs";
import { GoogleCloudSchedulerJob } from "../.gen/providers/google-beta/google-cloud-scheduler-job";
import { GoogleServiceAccount } from "../.gen/providers/google-beta/google-service-account";

export interface DailySchedulerConstructProps {
  readonly name: string;
  readonly project: string;
  readonly region: string;
  readonly schedule?: string;
  readonly timeZone?: string;
  readonly targetUri: string;
  readonly serviceAccount: GoogleServiceAccount;
  readonly dependsOn?: any[];
}

export class DailySchedulerConstruct extends Construct {
  public readonly job: GoogleCloudSchedulerJob;

  constructor(scope: Construct, id: string, props: DailySchedulerConstructProps) {
    super(scope, id);

    this.job = new GoogleCloudSchedulerJob(this, "dailySchedulerJob", {
      name: props.name,
      project: props.project,
      region: props.region,
      schedule: props.schedule ?? "0 0 * * *",
      timeZone: props.timeZone ?? "UTC",
      httpTarget: {
        httpMethod: "POST",
        uri: props.targetUri,
        oidcToken: {
          serviceAccountEmail: props.serviceAccount.email,
        },
      },
      dependsOn: props.dependsOn,
    });
  }
}
