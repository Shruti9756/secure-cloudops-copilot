# API image-security checkpoint

Verified on 15 October 2026 for the V0.4 AWS-platform branch.

## Successful CI evidence

- Branch: `codex/v04-aws-platform`.
- Commit: `0e4bf19eaefe93b015c80e8b7e8f532ee4eb2bd5`.
- Commit message: `fix(security): adopt validated Alpine API runtime`.
- Manual [GitHub Actions run 38776286863](https://github.com/Shruti9756/secure-cloudops-copilot/actions/runs/38776286863): completed successfully.
- All six jobs passed: API quality/tests, web quality/build, Terraform format/validation, secret scan, AWS OIDC identity smoke, and API image build/vulnerability scan.

The image-security job runs only for a manual workflow dispatch on the
specified repository and branch. Ordinary push and pull-request runs do
not establish image-security success. After changing source, start a new
manual run for the new commit; rerunning an old run uses its original commit.

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

## What remains unverified

This checkpoint does not prove AWS image publication, ECS deployment,
RDS/Valkey connectivity, controlled cloud migrations, Bedrock access, or
browser-to-answer staging behavior. Keep the on-demand staging runtime
off until those separate gates are reviewed.

Future publishing must publish the exact image that passed the scan. A
rebuild after a scan is a new artifact and requires its own validation.

The separate least-privileged publisher role has now been provisioned with
a clean follow-up Terraform plan, as recorded in the
[OIDC foundation](github-oidc.md#api-image-publisher-iam-foundation--applied).
GitHub assumption of that role and actual image publication are still
pending. The existing identity-only smoke role must not acquire publishing
or deployment rights.
