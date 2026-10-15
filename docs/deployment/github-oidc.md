# GitHub Actions AWS identity foundation

This foundation is managed separately by
`infra/terraform/environments/github-delivery`.

Its state key is `states/shared/github-delivery.tfstate` in the existing
private Terraform state bucket. It is not controlled by staging's
`runtime_enabled` switch.

## Initial scope

The initial identity checkpoint defines:

- The account-wide GitHub OIDC identity provider.
- The `secure-cloudops-github-oidc-smoke` login-test role.

The role has no attached permissions policy. Its trust requires audience
`sts.amazonaws.com` and this exact repository/branch subject:

`repo:Shruti9756@103516233/secure-cloudops-copilot@1323171008:ref:refs/heads/codex/v04-aws-platform`

The repository's immutable subject format was checked before defining trust.
Do not replace it with the older name-only format or a wildcard.

## Safety boundaries

Do not attach deployment, secret-reading, Terraform-state, or image-pushing
permissions to this smoke-test role.

The `AWS OIDC identity smoke test` job in `.github/workflows/ci.yml` runs
only for a manual `workflow_dispatch` on `codex/v04-aws-platform`.

It requests 15-minute credentials and verifies the exact AWS account,
assumed role, and run-specific session using `aws sts get-caller-identity`.
It does not build, push, deploy, read secrets, or change AWS resources.

Push and pull-request runs skip this AWS job. The other CI quality jobs
still run normally.

The workflow definition alone is not proof of successful authentication.
Record a successful manual run and its PASS message as test evidence.

Do not add long-lived AWS access keys to GitHub secrets.
Do not add OIDC token permissions to ordinary pull-request CI jobs.

Review this root's plan and IAM provisioning permissions before applying.
Do not apply the staging platform root to provision these identity resources.
Do not use `terraform destroy` on this shared identity foundation.

## Verified identity and image-security checkpoints

The manual [CI run 38776286863](https://github.com/Shruti9756/secure-cloudops-copilot/actions/runs/38776286863)
completed successfully on commit `0e4bf19eaefe93b015c80e8b7e8f532ee4eb2bd5`.
All six jobs passed, including the identity-only AWS OIDC smoke test and
the API image build and vulnerability scan. Image validation details are
recorded in [API image-security evidence](api-image-security.md).

This verifies authentication and build/scan checks, not image publication
or application deployment.

## API image-publisher IAM foundation — applied

The separate publisher role and its inline policy were applied on
15 October 2026: **2 added, 0 changed, 0 destroyed**. The role ARN is:

`arn:aws:iam::291667884598:role/secure-cloudops-github-api-image-publisher`

A follow-up `github-delivery` plan with `-detailed-exitcode` reported no
changes. The existing OIDC provider and identity-only smoke role were not
modified by this apply.

The publisher uses the same exact audience and immutable repository/branch
subject restrictions, with its own trust policy. Its permissions are limited
to publishing and inspecting images in `secure-cloudops-staging/api`, account
`291667884598`, region `us-east-1`.

The publisher policy grants no ECS deployment, IAM administration,
Secrets Manager, or Terraform-state access. ECR registry authentication
uses `ecr:GetAuthorizationToken` on `*`, restricted to `us-east-1`;
repository operations use the exact API repository ARN. A token permission
is not permission to push to every repository.

GitHub assumption of this publisher role and actual ECR publication have
not yet been verified. The successful earlier OIDC smoke job used the
separate identity-only role; it is not publisher-role test evidence.

Review the `github-delivery` plan before applying any new IAM resources.
Defining or creating a publisher role alone does not publish an image,
wire a workflow, start staging, or complete the delivery milestone.
