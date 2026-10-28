# API image security and publication checkpoints

Initial runtime validation was verified on 15 October 2026 for the V0.4
AWS-platform branch. The first API image publication was verified on
16 October 2026; the replacement publication below was verified on
18 October 2026 (Asia/Kolkata). Neither publication is a deployment.

## Successful CI evidence

- Branch: `codex/v04-aws-platform`.
- Commit: `0e4bf19eaefe93b015c80e8b7e8f532ee4eb2bd5`.
- Commit message: `fix(security): adopt validated Alpine API runtime`.
- Manual [GitHub Actions run 38776286863](https://github.com/Shruti9756/secure-cloudops-copilot/actions/runs/38776286863): completed successfully.
- All six jobs passed: API quality/tests, web quality/build, Terraform format/validation, secret scan, AWS OIDC identity smoke, and API image build/vulnerability scan.

The image-security job runs only for a manual workflow dispatch on the
specified repository and branch. Ordinary push and pull-request runs do
not establish image-security success. After changing image build inputs,
start a new manual run for the new commit; rerunning an old run uses its
original commit.

## Runtime changes and rationale

The API Dockerfile now uses `python:3.14.8-alpine3.24` and the existing
`linux/amd64` build target. It installs stable Alpine updates and the C++
runtime, then uses pinned uv with the unchanged production lockfile.
Dependency installation disallows source builds, Python downloads, and
cached source-built wheels. No compiler toolchain or glibc compatibility
layer was added.

PyJWT 2.14.0 and urllib3 2.8.0 were retained. Unneeded system pip and its
verified ensurepip bootstrap wheel were removed. The image retains the
non-root application user, packaged Alembic migrations, health check, and
FastAPI startup command.

The previous Debian image still reported 44 HIGH package findings across
eight distinct vulnerabilities after its Python findings were resolved.
The Alpine trial was evaluated as a separate candidate before promotion;
the result was not obtained by disabling OS scanning or suppressing those
findings.

## Local validation before promotion

- The `linux/amd64` runtime trial built successfully.
- Offline native checks exercised the PostgreSQL binary driver, AWS CRT and cryptography hashing, and locked dependency versions.
- Synthetic PDF and DOCX bytes were processed by the application's real extraction function.
- Alembic and its packaged configuration/migration files were present; no database migration was applied during these checks.
- The FastAPI process started and returned HTTP 200 with the expected `/health` payload, then shut down normally.
- A separate validation-only image ran the complete offline API suite: **615 passed, 6 deselected**. Live E2E tests remained excluded.
- The temporary validation image included development dependencies and is not the deployable runtime image.

The local Trivy 0.76.0 runtime report identified Alpine 3.24.2 and reported
zero HIGH/CRITICAL findings across 32 detected OS packages, 61 detected
Python packages, and the detected Rust components in uv/uvx. The scanner
exited with code 0. This was a point-in-time result, not a claim that all
severities were scanned or that future scans will remain clear.

## Security policy retained

- Scan OS and language packages, including detected Python dependencies.
- Select HIGH and CRITICAL severity findings.
- Keep `--ignore-unfixed=false` and `--ignorefile /dev/null`.
- Keep `--exit-code 1`; a qualifying finding fails the job.
- Save JSON, text, and diagnostic-log artifacts even when scanning fails. Current artifact retention is seven days.
- Do not add long-lived AWS keys or publish/deploy from pull-request CI.

## Replacement API image publication — verified 18 October 2026

The opt-in manual [CI run 39058503928](https://github.com/Shruti9756/secure-cloudops-copilot/actions/runs/39058503928)
completed successfully on branch `codex/v04-aws-platform`, commit
`ab3731499a44cf9d05cfa26ca751aa8cf3c89c6a`. All seven jobs passed,
including the API image build/vulnerability scan and `Publish scanned API
image to ECR`, with successful push/digest verification; publication was
not skipped.
The publication source includes the packaged `app.db.staging_identity`
module present in source ancestor `4a1762b`.

The operator's read-only ECR output confirmed this replacement record:

- Registry account and region: `291667884598`, `us-east-1`.
- Repository: `secure-cloudops-staging/api`.
- Immutable commit tag: `ab3731499a44cf9d05cfa26ca751aa8cf3c89c6a`.
- Registry manifest digest: `sha256:8b02063529e4dc1aa931b18c21bd14b902e55fb73f0cde6dcf09a5e9b7097c37`.
- Manifest media type: `application/vnd.docker.distribution.manifest.v2+json` (a single image manifest, not a platform index).
- Reported image size: `144764945` bytes.
- Push timestamp: `2026-10-18T00:03:56.526000+05:30`.

The exact replacement image reference is:

```text
291667884598.dkr.ecr.us-east-1.amazonaws.com/secure-cloudops-staging/api@sha256:8b02063529e4dc1aa931b18c21bd14b902e55fb73f0cde6dcf09a5e9b7097c37
```

This is registry-publication proof, not proof that ECS can pull/start the
replacement or that live database seeding, restricted grants, browser
authentication, or any application deployment succeeded. The separate
19 October local-image checkpoint below verifies offline import only.
The source-selection and runtime-off plan review is a configuration
checkpoint only. No runtime activation is implied.

### Source-selection review — 18 October 2026

The operator selected the verified replacement tag in the shared
`staging_api_image_tag` local in `ecs_api_task.tf`. The API, worker,
publisher, and database-bootstrap task definitions still consume that one
local; their runtime gates and zero service desired counts were not changed.
The reviewed public-hash assignment has a same-line `gitleaks:allow` marker.
That allowance is limited to this line, must never be used for credentials,
and does not replace the existing historical finding fingerprints.

The operator reported successful Terraform validation and a plan with
`runtime_enabled=false` and `staging_document_queue_backend="disabled"`:
**25 to add, 1 to change, 0 to destroy**. The additions were pending
foundation resources: log/subnet groups, IAM, Secrets Manager, SQS, and
publisher security-group resources. The in-place change was the database
security group's exclusive rule set. No RDS instance, Valkey replication
group, ECS service/task definition, or load balancer was listed.

This plan was not applied. These are operator-reported proposal results,
not an assertion about applied AWS state or a required count for future
plans. No new image build/publication is required solely for this
Terraform/documentation handoff; the approved application image remains
the verified `ab3731499a44cf9d05cfa26ca751aa8cf3c89c6a` artifact above.

### Published-image pull and offline import — verified 19 October 2026

The operator reported a successful Docker Desktop pull of the exact
replacement digest above, followed by all four guarded PASS messages.
Local inspection confirmed `linux/amd64`, configured user `app`, and the
expected complete ECR reference in `RepoDigests`. This is a real local
pull, not just registry metadata or an IAM simulation.

The check ran a disposable container as `app`, with networking disabled,
a read-only filesystem, image health check disabled, all capabilities
dropped, no-new-privileges, and no host mounts or explicitly supplied
environment settings. It used `--pull never` and a Python stdin entry
point instead of the image's normal FastAPI command. Before importing
`app.db.staging_identity`, the check replaced SQLAlchemy engine creation
and connection entry points with functions that fail on use.

The reported output confirmed the non-root import, expected module path
and `manager` constant, callable seed entry points, and the presence of
`/app/alembic.ini` and `/app/migrations/env.py`. The entry points were
inspected, not invoked. No database connection, migration, identity seed,
API server, or AWS runtime service was started by this check. Git status
was empty afterward.

For the local pull, Docker authentication was supplied through a
process-only `DOCKER_AUTH_CONFIG` override and cleared in `finally`
before container execution. No credential file or global Docker setting
was changed by this block. The earlier Windows credential-store failure
and missing `ecr:GetDownloadUrlForLayer` permission were separate issues;
the operator's corrected permission simulation reported both
`ecr:BatchGetImage` and `ecr:GetDownloadUrlForLayer` allowed before the
successful pull. This does not establish ECS execution-role permissions.

This 19 October checkpoint closed local packaging/import verification,
not the cloud identity or deployment hold. At that point, PostgreSQL
grants, staging Cognito-sub mapping, and live ECS image/network evidence
remained unverified. The separate 28 October bootstrap/cleanup checkpoint
in the [session runbook](staging-session-runbook.md) subsequently verified
the bootstrap task's image, migrations, restricted-role provisioning, and
runtime removal. No identity-seed execution was confirmed. No rebuild or
publication is needed solely to record these documentation checkpoints.

## API image publication — verified 16 October 2026

This earlier publication is retained as history. The replacement candidate
is recorded in the 18 October checkpoint above.

The opt-in manual [CI run 38788426230](https://github.com/Shruti9756/secure-cloudops-copilot/actions/runs/38788426230)
completed successfully on commit `998e4bfb58dd9c3f6463d4de7ae61b4db8a25235`,
on branch `codex/v04-aws-platform`. All seven jobs passed, including
`Publish scanned API image to ECR`; publication was not skipped.

The build/scan job retains only `contents: read` permission. After the
vulnerability gate passed, it exported the scanned image and transferred
it as a one-day artifact. The separate publisher downloaded that exact
artifact ID, checked its SHA-256 checksum, loaded the expected
`linux/amd64` image without rebuilding, and obtained temporary credentials
through the dedicated publisher role. Its identity check and
[push-and-ECR-digest verification step](https://github.com/Shruti9756/secure-cloudops-copilot/actions/runs/38788426230/job/116607014135)
both passed.

The operator's read-only `aws ecr describe-images` result confirmed:

- Registry account and region: `291667884598`, `us-east-1`.
- Repository: `secure-cloudops-staging/api`.
- Immutable commit tag: `998e4bfb58dd9c3f6463d4de7ae61b4db8a25235`.
- Registry manifest digest: `sha256:137956eac847118421725ce246b46bcb5466c90a899e3eb4682a15ac78923d20`.
- Follow-up manifest media type: `application/vnd.docker.distribution.manifest.v2+json` (a single image manifest, not a platform index).
- Push timestamp: `2026-10-16T00:18:35.301000+05:30`.

The image reference published at this earlier checkpoint was:

```text
291667884598.dkr.ecr.us-east-1.amazonaws.com/secure-cloudops-staging/api@sha256:137956eac847118421725ce246b46bcb5466c90a899e3eb4682a15ac78923d20
```

This historical registry digest identifies that published manifest; it is
not the Docker archive checksum or the GitHub artifact digest. Staging's
shared API image is selected by commit tag, not by a digest reference.
The replacement selection and plan review are described in the 18 October record
above; this older publication is retained as history, not presented as the
newly verified replacement.

`publish_api_image` defaults to `false`. Publication requires an explicit
manual selection on the approved repository and branch, and all required
quality/security jobs must succeed. Docker's temporary login directory is
set in the publishing step's environment, where GitHub permits
`runner.temp`; placing it in job-level `env` causes workflow startup
validation to fail.

Keep ECR tag immutability enabled. A different rebuilt image must not
overwrite an existing commit tag. Immutability does not guarantee permanent
retention: the repository lifecycle policy keeps only the newest ten
images, so confirm the selected image still exists before a future session.

## What remains unverified

Publication alone does not prove a cloud deployment. On 28 October, a
separate operator-run session verified the exact bootstrap image running
on Fargate, controlled RDS migrations and restricted-role provisioning,
and infrastructure removal followed by direct AWS absence checks. Its
disposable database was deleted. API/worker/publisher operation, application
database/cache connections, identity seeding, SQS ingestion, Bedrock
access, browser-to-answer behavior, and full running-service/API-origin
shutdown/rollback remain unverified. No application deployment was performed
by this publication workflow. Keep the on-demand runtime OFF until a new
session and its remaining gates are explicitly approved.

Every publication must use the exact image that passed its scan. A
rebuild after a scan is a new artifact and requires its own validation.

The separate least-privileged publisher role was provisioned with a clean
follow-up Terraform plan, as recorded in the
[OIDC foundation](github-oidc.md#api-image-publisher-iam-foundation--applied).
Its GitHub authentication and API image publication are verified by the
publication runs above. The existing identity-only smoke role must not acquire
publishing or deployment rights.
