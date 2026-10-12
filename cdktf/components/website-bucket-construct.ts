import { Construct } from "constructs";
import { GoogleStorageBucket } from "../.gen/providers/google-beta/google-storage-bucket";
import { GoogleStorageBucketIamMember } from "../.gen/providers/google-beta/google-storage-bucket-iam-member";
import { StringResource } from "../.gen/providers/random/string-resource";
import { GoogleServiceAccount } from "../.gen/providers/google-beta/google-service-account";

export interface WebsiteBucketConstructProps {
  readonly project: string;
  readonly region: string;
  readonly functionServiceAccount?: GoogleServiceAccount;
  readonly dependsOn?: any[];
}

export class WebsiteBucketConstruct extends Construct {
  public readonly bucket: GoogleStorageBucket;

  constructor(scope: Construct, id: string, props: WebsiteBucketConstructProps) {
    super(scope, id);

    const bucketSuffix = new StringResource(this, "websiteBucketPrefix", {
      length: 8,
      special: false,
      upper: false,
    });

    this.bucket = new GoogleStorageBucket(this, "websiteBucket", {
      name: `report-${bucketSuffix.result}`,
      project: props.project,
      location: props.region,
      storageClass: "REGIONAL",
      forceDestroy: true,
      uniformBucketLevelAccess: true,
      website: {
        mainPageSuffix: "index.html",
        notFoundPage: "index.html",
      },
      dependsOn: props.dependsOn,
    });

    // Allow public read access to serve static website content
    new GoogleStorageBucketIamMember(this, "publicRead", {
      bucket: this.bucket.name,
      role: "roles/storage.objectViewer",
      member: "allUsers",
    });

    if (props.functionServiceAccount) {
      new GoogleStorageBucketIamMember(this, "functionAdmin", {
        bucket: this.bucket.name,
        role: "roles/storage.objectAdmin",
        member: `serviceAccount:${props.functionServiceAccount.email}`,
      });
    }
  }
}
