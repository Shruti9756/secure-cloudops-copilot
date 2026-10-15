# API image security and publication checkpoints

Initial runtime validation was verified on 15 October 2026 for the V0.4
AWS-platform branch. API image publication was verified on 16 October 2026
(Asia/Kolkata).

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

## API image publication — verified 16 October 2026

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
- Push timestamp: `2026-10-16T00:18:35.301000+05:30`.

The exact published image reference is:

```text
291667884598.dkr.ecr.us-east-1.amazonaws.com/secure-cloudops-staging/api@sha256:137956eac847118421725ce246b46bcb5466c90a899e3eb4682a15ac78923d20
```

This registry digest identifies the published manifest; it is not the
Docker archive checksum or the GitHub artifact digest. Staging's task
configuration currently selects its shared API image by commit tag, not
by a digest reference. Selecting the newly verified tag and reviewing a
runtime-off plan is a separate configuration handoff, not a deployment.

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

Publication does not prove ECS can pull or start the image, RDS/Valkey
connectivity, controlled cloud migrations, SQS ingestion, Bedrock access,
browser-to-answer staging behavior, rollback, or session shutdown. No
application deployment was performed by this workflow. Keep the on-demand
staging runtime off until those separate gates are reviewed.

Every publication must use the exact image that passed its scan. A
rebuild after a scan is a new artifact and requires its own validation.

The separate least-privileged publisher role was provisioned with a clean
follow-up Terraform plan, as recorded in the
[OIDC foundation](github-oidc.md#api-image-publisher-iam-foundation--applied).
Its GitHub authentication and API image publication are now verified by
the later run above. The existing identity-only smoke role must not acquire
publishing or deployment rights.
