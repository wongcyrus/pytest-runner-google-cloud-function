import { Construct } from "constructs";
import { GoogleStorageBucket } from "../.gen/providers/google-beta/google-storage-bucket";
import { GoogleStorageBucketIamMember } from "../.gen/providers/google-beta/google-storage-bucket-iam-member";
import { GoogleServiceAccount } from "../.gen/providers/google-beta/google-service-account";
import { GoogleProjectService } from "../.gen/providers/google-beta/google-project-service";
import { StringResource } from "../.gen/providers/random/string-resource";

export class SubmissionBucketConstruct extends Construct {
    public readonly bucket: GoogleStorageBucket;

    constructor(scope: Construct, id: string, props: {
        project: string; region: string; dependsOn: GoogleProjectService[];
    }) {
        super(scope, id);
        const suffix = new StringResource(this, "suffix", {
            length: 16, special: false, upper: false,
        });
        this.bucket = new GoogleStorageBucket(this, "bucket", {
            name: `submissions-${suffix.result}`,
            project: props.project,
            location: props.region,
            uniformBucketLevelAccess: true,
            publicAccessPrevention: "enforced",
            forceDestroy: false,
            dependsOn: props.dependsOn,
        });
    }

    grantCreator(account: GoogleServiceAccount): GoogleStorageBucketIamMember {
        return new GoogleStorageBucketIamMember(this, "runner-creator", {
            bucket: this.bucket.name,
            role: "roles/storage.objectCreator",
            member: `serviceAccount:${account.email}`,
        });
    }
}
