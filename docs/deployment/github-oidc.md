# GitHub Actions AWS identity foundation

This foundation is managed separately by
`infra/terraform/environments/github-delivery`.

Its state key is `states/shared/github-delivery.tfstate` in the existing
private Terraform state bucket. It is not controlled by staging's
`runtime_enabled` switch.

## Initial scope

The configuration defines only:

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