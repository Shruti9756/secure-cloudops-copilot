# ADR-0003: Host the staging frontend as a static site

**Status:** Accepted
**Date:** 28 September 2026

## Context

V0.4 needs an HTTPS staging website without requiring a purchased domain or an always-running frontend container. The Next.js frontend successfully builds as a static export. The staging database, cache, and backend containers are intended to run only during planned test sessions.

## Decision

Build the staging frontend with `WEB_OUTPUT_MODE=export`. Store the generated website files in a dedicated private S3 bucket, separate from the bucket for redacted tenant documents. Serve the website through CloudFront using origin access control and the AWS-provided `cloudfront.net` HTTPS address.

This refines ADR-0001 for the frontend only. The API and worker remain planned as ECS Fargate containers. Frontend hosting is separate from the `runtime_enabled` switch for the database, cache, and backend.

## Consequences

- No frontend ECS task needs to run while the staging backend is off.
- S3 and CloudFront may still incur charges; `runtime_enabled=false` does not mean zero cost.
- The static export cannot use Next.js server-only features. Dynamic application work remains in the API.
- Browser-visible `NEXT_PUBLIC_*` settings must be correct when the staging frontend is built; do not upload a build made with local-development URLs.
- The exported Cognito callback file is `auth/callback.html`. Its eventual Cognito redirect URL and CloudFront routing must match exactly.
- This decision does not create a bucket, distribution, Cognito client, or running backend. Each deployment step requires its own reviewed Terraform plan.