import { Testing, TerraformStack } from "cdktn";
import { ArchiveProvider } from "../.gen/providers/archive/provider";
import { RandomProvider } from "../.gen/providers/random/provider";
import { GoogleBetaProvider } from "../.gen/providers/google-beta/provider";
import { CloudFunctionConstruct } from "../components/cloud-function-construct";
import { CloudFunctionDeploymentConstruct } from "../components/cloud-function-deployment-construct";
import { SubmissionBucketConstruct } from "../components/submission-bucket-construct";
import { WebsiteBucketConstruct } from "../components/website-bucket-construct";

describe("Private submission storage", () => {
  it("keeps source private and persistent with create-only runner IAM and deployment ordering", async () => {
    const stack = new TerraformStack(Testing.app(), "storage-test");
    new GoogleBetaProvider(stack, "google", {});
    const deployment = new CloudFunctionDeploymentConstruct(stack, "deployment", {
      project: "pytest-runner-test-2627",
      region: "asia-east2",
      archiveProvider: new ArchiveProvider(stack, "archive", {}),
      randomProvider: new RandomProvider(stack, "random", {}),
    });
    const submissions = new SubmissionBucketConstruct(stack, "submissions", {
      project: deployment.project, region: deployment.region, dependsOn: deployment.services,
    });
    const runner = await CloudFunctionConstruct.create(stack, "runner", {
      functionName: "pytestrunner", entryPoint: "pytestrunner", runtime: "python311",
      cloudFunctionDeploymentConstruct: deployment,
      submissionBucket: submissions,
      environmentVariables: { SUBMISSION_BUCKET: submissions.bucket.name },
    });
    new WebsiteBucketConstruct(stack, "reports", {
      project: deployment.project, region: deployment.region,
      functionServiceAccount: runner.serviceAccount,
    });
    const resources = JSON.parse(Testing.synth(stack)).resource;
    const [submissionBucketId] = Object.entries(resources.google_storage_bucket)
      .find(([, value]) => (value as any).public_access_prevention === "enforced")!;
    const submissionBucketName = `\${google_storage_bucket.${submissionBucketId}.name}`;
    const buckets = Object.values(resources.google_storage_bucket) as any[];
    const bucket = buckets.find(value => value.public_access_prevention === "enforced")!;
    expect(bucket).toBeDefined();
    expect(bucket.uniform_bucket_level_access).toBe(true);
    expect(bucket.force_destroy).toBe(false);
    expect(bucket.lifecycle_rule).toBeUndefined();
    expect(bucket.website).toBeUndefined();
    expect(bucket.project).toBe("pytest-runner-test-2627");
    expect(buckets).toHaveLength(3);
    expect(buckets.find(value => value.lifecycle_rule)?.lifecycle_rule[0].condition.age).toBe(1);
    const bindings = Object.entries(resources.google_storage_bucket_iam_member) as [string, any][];
    const [creatorId, creator] = bindings.find(([, value]) => value.bucket === submissionBucketName)!;
    expect(creator.role).toBe("roles/storage.objectCreator");
    expect(bindings.filter(([, value]) => value.bucket === submissionBucketName)).toHaveLength(1);
    const fn = Object.values(resources.google_cloudfunctions2_function)[0] as any;
    expect(creator.member).toBe(`serviceAccount:${fn.service_config.service_account_email}`);
    expect(fn.service_config.environment_variables.SUBMISSION_BUCKET).toBe(submissionBucketName);
    expect(fn.depends_on).toContain(`google_storage_bucket_iam_member.${creatorId}`);
    const [sourceBucketId] = Object.entries(resources.google_storage_bucket)
      .find(([, value]) => (value as any).lifecycle_rule)!;
    expect(fn.build_config.source.storage_source.bucket)
      .toBe(`\${google_storage_bucket.${sourceBucketId}.name}`);
    expect(fn.build_config.source.storage_source.bucket).not.toBe(submissionBucketName);
  });

  it("uses separate bucket identities for separate deployment stacks", () => {
    const names = ["pytest-runner-test", "pytest-runner"].map(id => {
      const stack = new TerraformStack(Testing.app(), id);
      new GoogleBetaProvider(stack, "google", {});
      new RandomProvider(stack, "random", {});
      new SubmissionBucketConstruct(stack, "submissions", {
        project: `${id}-2627`, region: "asia-east2", dependsOn: [],
      });
      const resource = JSON.parse(Testing.synth(stack)).resource;
      return Object.values(resource.google_storage_bucket)[0] as any;
    });
    expect(names[0].project).toBe("pytest-runner-test-2627");
    expect(names[1].project).toBe("pytest-runner-2627");
    expect(names.every(bucket => bucket.name.startsWith("submissions-"))).toBe(true);
  });
});
