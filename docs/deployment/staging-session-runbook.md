# Controlled staging-session runbook

Prepared on 16 October 2026 for `codex/v04-aws-platform`.

**Status: static website publication and two HTTPS HTML routes verified on
17 October 2026; replacement API image publication verified on 18 October
2026; exact published-image local pull and offline identity-module import
verified on 19 October 2026; six task-operator IAM simulations reported
allowed on 19 October 2026, followed by the complete 22-check IAM
checkpoint reported on 20 October 2026. On 28 October, the first controlled
infrastructure attempt partially created resources, encountered two IAM
denials, and was cleaned up; runtime OFF was independently verified.
Database bootstrap, identity seeding, application startup, and a full
service-start/shutdown cycle remain untested on AWS. This document does
not approve another live session. Do not execute the future live phases yet.** Keep
`runtime_enabled=false`, `staging_document_queue_backend="disabled"`,
`staging_api_connection_mode="disabled"`, and all ECS service desired
counts at zero while resolving the holds below.

A runbook is an operator checklist, not an automatically executed script.
This companion defines the service order and checks; the
[on-demand runtime guide](staging-on-demand.md) owns the Terraform and
one-off database-bootstrap instructions. Use only synthetic, disposable
staging data. Never copy this procedure into development or production.

## 1. Fixed scope and approved image

| Item | Expected value |
| --- | --- |
| Local AWS profile | `securecloudops-dev` |
| AWS account / region | `291667884598` / `us-east-1` |
| ECS cluster | `secure-cloudops-staging-cluster` |
| Platform Terraform root | `infra/terraform/environments/staging` |
| Frontend/identity Terraform root | `infra/terraform/environments/staging-frontend` |
| Image repository | `291667884598.dkr.ecr.us-east-1.amazonaws.com/secure-cloudops-staging/api` |
| Configured commit tag (not deployed) | `ab3731499a44cf9d05cfa26ca751aa8cf3c89c6a` |
| Verified top-level registry digest | `sha256:8b02063529e4dc1aa931b18c21bd14b902e55fb73f0cde6dcf09a5e9b7097c37` |
| Verified manifest media type | `application/vnd.docker.distribution.manifest.v2+json` (single image manifest) |

[Publication evidence](api-image-security.md#replacement-api-image-publication--verified-18-october-2026)
records the successful CI run and operator's ECR lookup. The API, worker,
database bootstrap, and outbox publisher share `local.staging_api_image_tag`
in `ecs_api_task.tf`. A later documentation or Terraform-only commit does
not require rebuilding an unchanged image.

On 18 October, the operator selected this shared tag in the local Terraform
source and reported successful validation. The explicit runtime-off,
queue-disabled plan showed **25 to add, 1 to change, 0 to destroy**. Its
changes were pending foundation resources and the database security group's
exclusive rule set, not RDS/Valkey instances, ECS services/task definitions,
or a load balancer. Counts describe this unapplied proposal, not resources
created or a mandatory count for future plans. No apply was performed.

This source-selection checkpoint does not deploy any service. The
replacement image's presence in ECR is not evidence that ECS pulled it or
that the staging identity seed executed inside it. On 19 October, the
operator separately pulled the exact digest locally and passed the
[offline import check](api-image-security.md#published-image-pull-and-offline-import--verified-19-october-2026):
`linux/amd64`, configured/non-root `app` user, expected module and migration
files, and import without database access. The temporary authentication
override was cleared before the network-disabled container check. No
seed function, API server, migration, or AWS runtime service was started.
Keep all live-phase holds below in force; a local pull does not prove an
ECS execution role can pull or start this image.

Before a live session, re-confirm that the tag still exists and maps to
that digest; repository lifecycle rules can expire immutable images.
Also inspect the manifest media type. A manifest is the registry's image
description; an index/manifest list can wrap platform-specific manifests.
If the top object is an index, resolve and record its unique approved
`linux/amd64` image-manifest digest before checking ECS's `imageDigest`.
Do not confuse a platform manifest with the top-level index, a config
digest, or an archive checksum. Missing or ambiguous manifest evidence is
a hold, not permission to accept an arbitrary different digest or rebuild.

## 2. Choose the session's purpose before spending

| Session | Permitted objective | Still prohibited |
| --- | --- | --- |
| Planning/preflight (current) | Read configuration, validate, inspect identity/image metadata, review plans, and build the static frontend locally | Apply, create runtime resources, scale services up, attach the API origin, upload test data |
| Static website checkpoint (completed) | Publish the reviewed 29-file export to the existing private bucket; verify home/callback HTTP 200 HTML through CloudFront | Runtime start, API attachment, knowledge-document uploads, and claims of working sign-in or AI |
| Future database/identity-only test | Bootstrap the database and run the restricted synthetic identity seed; keep every application service at zero, then shut down | API/worker/publisher start, API-origin attachment, uploads, AI calls, and claims of working browser sign-in |
| Future non-AI connectivity test | Bootstrap the private database; run only the API; verify ALB readiness and approved HTTPS status route | Worker/publisher start, uploads, embedding, chat, and claiming full V0.4 success |
| Future full staging test | Approved identity/workspace setup, API, SQS worker/publisher, synthetic ingestion, and cited answers | Unreviewed providers, development identities, real documents, unbounded retries |

The operator must choose the purpose, maximum session duration, current
credit/budget limits, and a cleanup owner before a runtime-on apply.
RDS, Valkey, the ALB, Fargate, and public IPv4 addresses can incur charges;
zero ECS tasks does not stop the database/cache/load-balancer costs.
A budget alert is not an automatic spending cap. Do not upgrade the AWS
account plan or buy extra capacity as an access workaround.

## 3. Current holds: not cleared by successful image publication

- **Provider/topology:** `ecs_api_task.tf` and `ecs_worker_task.tf` do not
  set `EMBEDDING_PROVIDER` or `OLLAMA_BASE_URL`. Defaults select Ollama at
  loopback, and no staging Ollama service/sidecar is defined. The current
  API `get_chat_provider()` returns `OllamaChatClient`. The last reported
  Bedrock access check was denied; even a later Bedrock approval alone
  would not configure these tasks or change the API's chat dependency.
  Do not start document processing until a reachable, tested provider path
  and matching document/query embedding model are reviewed.
- **Application identities/data:** `app.db.bootstrap` migrates the schema
  and provisions the restricted application database role, not tenants,
  Cognito-to-application users, or memberships. The existing identity
  script requires a tenant first. The shipped Dockerfile does not package
  `scripts/` or `docs/demo-data/`; do not invent ECS commands such as
  `python -m scripts.bootstrap_cognito_identity`. A separately reviewed
  synthetic seeding/provisioning path is required for authenticated tests.
  The operator has now added `app.db.staging_identity` and reported 60
  targeted tests and 675 total unit tests passing, with six E2E tests
  deselected. The 18 October image was built and scanned from a commit
  containing that module. On 19 October, the operator verified its import
  as non-root in the exact published image, locally with networking
  disabled and database-access guards. These offline/publication checks
  do not clear the live hold. The dedicated runtime-gated identity-seed
  task definition is now committed, and the operator found the intended
  staging user's actual `sub` privately after completing its password
  change. PostgreSQL grants and the actual database mapping remain
  unverified; the bounded launch/observation commands still need review
  before a paid session. Never reuse the administrator bootstrap task with
  a command override to run this seed.
- **Browser integration (static HTML verified):** The dedicated staging
  Cognito/frontend outputs match the local API identity/origin inputs, and
  the reviewed export is published with home/callback HTTP 200 HTML checks
  recorded in section 4. A separate read-only browser check observed styled
  desktop layout and the callback's expected missing-login state. Full
  browser workflows, sign-in, and application membership remain unverified.
  Source defaults being blank does not mean a staging pool is absent;
  static delivery and deployed Cognito resources do not prove a working
  authenticated application.
- **Private document storage:** `document_storage_backend` defaults to
  `disabled`, and the staging API task does not configure its S3 backend
  or document bucket. A basic upload test is not proof of the V0.4 S3
  storage requirement. Review an approved private staging document store,
  task permissions, redacted-object references, and authorized download
  behavior separately. The static website bucket is not a document store;
  do not put uploaded documents into the CloudFront-served frontend bucket.
- **Live safeguards:** Confirm scoped operator permissions, task roles,
  the approved manifest/platform mapping, and a complete shutdown plan.
  None is proven merely by `terraform validate` or an ECS task recipe.

These holds do not prevent reviewing a future non-AI connectivity session,
but that session still requires its own explicit approval and cost window.
Do not start the worker against pending documents with an unavailable
provider: processing attempts may be consumed even while the container
continues running.

## 4. Safe preflight now — no runtime apply

From `C:\Users\Shru\Documents\AI+AWS`, run only individually selected
read-only/preflight commands, checking each exit code before continuing:

```powershell
aws sts get-caller-identity --profile securecloudops-dev --query Account --output text
aws freetier get-account-plan-state --region us-east-1 --profile securecloudops-dev --output json
aws ecr describe-images --registry-id 291667884598 --repository-name secure-cloudops-staging/api --image-ids imageTag=ab3731499a44cf9d05cfa26ca751aa8cf3c89c6a --region us-east-1 --profile securecloudops-dev --query 'imageDetails[0].{Digest:imageDigest,MediaType:imageManifestMediaType,Tags:imageTags}' --output json
terraform -chdir=infra\terraform\environments\staging-frontend output -json frontend_hosting
terraform -chdir=infra\terraform\environments\staging-frontend output -json staging_identity
terraform -chdir=infra\terraform\environments\staging validate
```

Stop on any failed command, wrong account/region, unexpected image, or
unavailable output. An expired login is not a reason to change IAM. Do
not dump Terraform state or secret values to diagnose these checks.

Set `$env:AWS_PROFILE = 'securecloudops-dev'` in the current PowerShell session
before a platform plan. Review the explicit runtime-off plan; the one
reviewed for the image handoff showed **25 adds, 1 change, 0 destroys**.
Those were unapplied supporting resources, not running database/cache,
ECS services/task definitions, or an ALB. Counts are historical evidence,
not a target or permission to apply. An off-mode apply can still create
Secrets Manager secrets and other persistent resources with ongoing cost.

### Preflight handoff verified on 16 October 2026

The operator's ECR lookup returned the approved tag/digest above with media
type `application/vnd.docker.distribution.manifest.v2+json`: a single image
manifest, not an index. No child-platform digest resolution is needed for
this object. This is registry metadata evidence, not proof of an ECS pull
or the platform of a running task.

The frontend/identity outputs returned these public configuration values:

| Setting | Verified value |
| --- | --- |
| Frontend bucket | `secure-cloudops-staging-web-291667884598-us-east-1` |
| CloudFront distribution | `E2JZ8IOOSQ6MB9` |
| Website origin / frontend API base URL | `https://d28yij2tl8eb0p.cloudfront.net` |
| Cognito issuer (API setting) | `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_cgRH4viJI` |
| Public Cognito app client ID | `4snku1lu0f41r0u5datrlsovuj` |
| Browser managed-login base URL | `https://secure-cloudops-copilot-staging-291667884598.auth.us-east-1.amazoncognito.com` |
| Browser callback URL | `https://d28yij2tl8eb0p.cloudfront.net/auth/callback.html` |
| Browser logout URL | `https://d28yij2tl8eb0p.cloudfront.net/` |

The existing ignored platform `terraform.tfvars` already matches the
issuer, app client ID, and website origin, with runtime off and queue mode
disabled; do not append duplicate assignments. The frontend API base is
the origin alone: browser code adds `/api/v1/...` itself. Browser login
uses the managed-login URL, not the API's Cognito issuer URL.

Next.js public settings are embedded when building the frontend. A local
staging export may use process-only overrides while preserving `.env.local`;
restore the previous process values afterward. These addresses/client IDs
are public configuration, never credentials. Suppress the development
workspace default until a real staging membership exists: a process override
containing one space is trimmed to no default by the application. Removing
that override before the build would allow `.env.local` to supply its default.
A successful export is only local build evidence: no frontend upload,
working browser login, API attachment, provider access, or runtime start
is established by this checkpoint.

### Local staging frontend export verified on 17 October 2026

The operator reported successful `npm.cmd run lint` and `npm.cmd run build`
with Next.js 16.3.5 and `WEB_OUTPUT_MODE=export`. The guarded local check
confirmed `out/index.html` and `out/auth/callback.html` exist, and found
the expected staging API base URL, managed-login URL, public app client ID,
and callback URL as exact quoted literals in the exported JavaScript.
The command finished with its local-export PASS message and Git status
showed only the two intended Markdown documentation changes.

The procedure temporarily overrides six process environment variables and
restores their previous values and the working directory in `finally`.
It does not edit `.env.local`; Next.js listing that file in its build log
does not mean it overrides explicitly supplied process settings. The single
space workspace override deliberately produces no default workspace rather
than inheriting a development value. Generated `.next/` and `out/` files are
ignored by Git and are not part of the documentation commit.

No S3 upload, CloudFront invalidation, Terraform apply, or ECS service start
was part of this command. This is local build/configuration evidence only,
not proof of deployed website contents, successful sign-in, API connectivity,
or AI functionality. Keep runtime and the CloudFront API connection disabled.

### Static-website upload preview verified on 17 October 2026

The operator's owner-checked bucket listing returned no objects. The
distribution was deployed with the expected single S3 origin and no API
cache behavior. All 29 dry-run uploads targeted the frontend bucket; the
reviewed export fingerprint matched. No upload/deletion occurred.

### Static website publication and HTML delivery verified on 17 October 2026

The operator completed the [create-only first publication](staging-frontend-publication.md):
13 JavaScript/CSS assets, 12 Next.js text files, and four HTML files, with
`index.html` last. Every object passed checksum, size, content-type,
cache-control, and AES256 checks, and the final inventory matched all 29
reviewed keys/sizes. The website home page and `/auth/callback.html` then
both returned HTTP 200 HTML through CloudFront.

The upload block is now historical: do not rerun it on the populated bucket.
No API attachment, invalidation, Terraform apply, or service start was part
of the reported operation. A later read-only browser check confirmed limited
desktop styling/layout and callback JavaScript execution without signing in;
full browser workflows, sign-in/API/AI, and runtime shutdown remain unverified.
This milestone does not authorize any runtime phase below.

### Identity and task-operator checkpoint reported on 19 October 2026

The operator reported the intended staging Cognito user as confirmed and
enabled after changing its temporary password, and located its actual
`sub` in the correct staging pool. No email, subject value, password, JWT,
or callback query string is recorded here. The browser callback still
reported a generic sign-in failure with the API connection disabled;
successful OAuth token exchange and an accepted application session have
not been established.

The account-plan read reported `FREE`, `ACTIVE`, **USD 137.77** remaining
credits, and plan expiration `2027-01-29T09:35:16.346000+00:00`. This is a
point-in-time account-plan result, not a spending cap or a guarantee about
every credit grant's expiration. Refresh it before an approved cost window.

After a manual amendment to the existing customer-managed
`SecureCloudOpsStagingEcsClusterTerraform` policy, all six operator
simulations reported `allowed`: `RunTask` for each of the database-bootstrap
and identity-seed families, `DescribeTasks`, `StopTask`, `ListTasks`, and
`DescribeTaskDefinition`. The proposed amendment is intended to preserve
cluster management, restrict its new launch grant to those two families
in the exact staging cluster, permit inspecting/stopping that cluster's
tasks, and add task-list/definition metadata reads. Positive simulations
alone do not prove these scope boundaries or the active policy document.
This is not evidence of a real launch,
Terraform create/delete permissions, or a least-privilege operator identity;
the inherited `Developers` group includes broader permissions.

The logging evidence is deliberately recorded as inconsistent: principal
simulation returned `implicitDeny` for the hypothetical seed log stream,
while the inherited `CloudWatchFullAccess` policy allowed `logs:*` and no
user permissions boundary was attached. A real `GetLogEvents` request in
the API log group, targeting a fresh diagnostic stream name with a
`[0,1)` millisecond time range and displaying only `length(events)`, exited
zero and returned zero events. This does not verify the anticipated
missing-resource error or retrieval of future bootstrap/seed success logs. No additional logging
grant was made; verify the actual task's log stream during a separately
approved session. Unrelated missing-context keys are not values to invent
just to obtain an allowed simulation.

No runtime apply, ECS task launch, application identity seed, or service
start was reported as part of these checks. Do not reuse the original
ten-row gate as a complete readiness test. The provisioning/runtime-off
IAM review continued at the checkpoint below; separately reviewed
standalone-task launch and cleanup commands remain required.

### Provisioning and runtime-off IAM checkpoint reported on 20 October 2026

The operator reported that default version `v3` of the existing
`SecureCloudOpsStagingEcsClusterTerraform` managed policy matched the
reviewed 20-statement document. The normalized-document comparison
preserved the five earlier statements and checked the complete replacement,
not merely its statement count. No new policy attachment was required.

All 20 positive statement groups simulated as allowed, covering the
existing cluster/setup-task operations and the added ECS task/service,
RDS, Valkey, secret, and SQS operations. This includes the RDS-instance,
Valkey-replication-group, ECS-service deletion and task-definition
deregistration needed for the reviewed runtime-off cycle. The two negative
checks also passed: direct `RunTask` for the API family was denied, and
task-definition deregistration outside `us-east-1` was denied. The latter
action uses `Resource: "*"` because its IAM action does not support
task-definition resource scoping; it is not family-restricted within the
approved region.

The checks used synthetic future resource identifiers, performed no
tested create/delete/run operation, and retrieved no secret values.
The new grants do not add deletion of persistent queues, application
secrets or subnet groups, SQS message operations, master-password
retrieval, or customer-managed KMS-key permissions. They target the
reviewed first create/runtime-off cycle, not arbitrary later upgrades or
token rotation. Existing broader inherited grants were not removed.

This is simulated authorization evidence, not proof of live provisioning,
Free-plan service eligibility, actual task execution, successful seed-log
retrieval, or cost-free operation. The two security-group exclusive-rule
updates still need full before/after review, and a fresh credit check,
explicit session purpose/cost window, bounded task observation, and
shutdown procedure are still required before any credit-consuming runtime apply.

### Saved-plan security-group review reported on 20 October 2026

The operator's refreshed account-plan result was `FREE`, `ACTIVE`, with
USD **137.74** remaining and the same 29 January 2027 plan expiration.
This is a point-in-time balance, not a session spending cap. No account
upgrade, runtime apply, or task launch was part of this checkpoint.

Validation succeeded and the saved runtime-on, queue-disabled preview
again reported **46 additions, 2 in-place updates, and 0 deletes**. The
printed managed-resource list matched the earlier proposal. The temporary
plan is sensitive, is not a source artifact, and is not approved for
execution merely because it was saved or inspected.

The focused before/after JSON and owner-checked live rule descriptions
confirmed the following existing-rule preservation:

| Rule set | Existing rules retained | Intended addition |
| --- | --- | --- |
| API ingress | One TCP 8000 rule from the existing load-balancer security group | One TCP 8000 rule from the new private API ALB security group |
| API egress | All three rules: HTTPS 443, PostgreSQL 5432, and cache 6379 | None |
| Database ingress | Both TCP 5432 rules from API and worker security groups | One TCP 5432 rule from the publisher security group |
| Database egress | Empty | None |

The new ingress IDs appeared as `null` with corresponding
`after_unknown=true` entries because the rules do not exist yet. Comparing
those unknown entries with the actual source references identifies the
private-ALB and publisher additions; it is not proof those rules were
created. The existing older load-balancer API ingress remains permitted,
so do not describe the resulting API group as allowing only the new ALB.
The existing `0.0.0.0/0` rule is outbound HTTPS, not public inbound API or
PostgreSQL access. Both inspected groups belonged to the expected account.

This clears the focused plan-level SG ownership review, not live network
connectivity. Retain the other relevant session gates: exact standalone
task launch/observation/shutdown commands, actual registered task-role and
image checks, explicit test purpose/duration, current pricing/credit
review, and separate authorization before any runtime apply.

### Runtime-on preview reported on 19 October 2026

The operator's staging validation succeeded. A speculative plan with
`runtime_enabled=true` and `staging_document_queue_backend="disabled"`
reported **46 additions, 2 in-place changes, and 0 destroys**. RDS was
`db.t4g.micro`, 20 GiB, and not publicly accessible; Valkey was
`cache.t4g.micro`; the ALB was internal. The API and worker services both
had desired count zero. The two updates were the API/database security
groups' exclusive-rule resources, whose full before/after ownership still
needs review before apply.

Disabled queue mode does not remove the persistent SQS/DLQ definitions
or publisher role/log/security-group foundations from this plan. No
publisher ECS service or publisher task definition was proposed. Deferred
IAM-policy-document reads are data evaluation, not additional running
services. This preview did not apply anything, save an approved execution
plan, or establish create/delete authorization. The later 20 October IAM
checkpoint records the consolidated policy review and simulations; it does
not approve applying this preview or replace the remaining session gates.

### Controlled attempt, verified cleanup, and IAM repairs — 28 October 2026

The operator approved a database/identity-only test with a two-hour target,
a USD 1 planning allowance, and personal responsibility for cleanup. The
recorded session start was **19:00:43 IST**, the cleanup-start cutoff was
20:00:43 IST, and the finish target was 21:00:43 IST. These were operator
targets, not an automatic shutdown or a guaranteed spending cap. The
pre-session account-plan read reported `FREE`, `ACTIVE`, **USD 137.53**
remaining, with plan expiration `2027-01-29T09:35:16.346000+00:00`.
That balance is not a final session-cost measurement.

The fresh saved plan contained **46 additions, 2 updates, and 0 destroys**.
Its API/worker services had desired count zero, publisher runtime was
absent, RDS was private, the ALB was internal, and the live CloudFront
distribution remained S3-only with no API routing. The operator applied
that reviewed plan, but provisioning stopped after these real IAM denials:

- `elasticache:CreateReplicationGroup` required authorization for
  `arn:aws:elasticache:us-east-1:291667884598:parametergroup:*`; the reference
  statement allowed only the named `default.valkey7` group. The Terraform
  resource does not explicitly set `parameter_group_name`.
- RDS creation progressed, but the provider's subsequent
  `rds:DescribeDBInstances` lookup required
  `arn:aws:rds:us-east-1:291667884598:db:*`, not only the named database ARN.
  Provider 6.66.0 stores the generated database resource ID and reads it
  through a `dbi-resource-id` filter. The earlier simulations missed this
  request/resource distinction.

This was a partial deployment, not an automatic rollback. The internal
ALB was created. After adding an isolated read-only
`ReadDatabaseMetadataInRegion` statement for `rds:DescribeDBInstances` on
the regional/account `db:*` ARN, the operator confirmed the database was
`available`, not public, and tracked by Terraform. Its create/delete grants
were not widened. No ECS services or task definitions were created in this
attempt, no Fargate tasks were launched, and bootstrap/identity seeding did
not run. No API origin was attached to CloudFront.

The operator reviewed a fresh runtime-off, queue-disabled plan with
**0 additions, 1 update, and 13 destroys**, then applied it successfully.
It removed RDS; the internal ALB, listener, target group and runtime security
resources; the identity-seed log group/execution role/policy; and the
runtime-only worker secret-read policy. The API exclusive-rule update
removed the private-ALB ingress reference. Cleanup completed at
**19:29:11 IST**, before the original cutoff.

The separate operator-run verification reported:

- Fresh runtime-off/queue-disabled Terraform plan: **no changes**.
- Exact RDS lookup: `DBInstanceNotFound`.
- Exact ALB lookup: `LoadBalancerNotFound`.
- Exact Valkey replication-group lookup: `ReplicationGroupNotFoundFault`.
- Staging ECS cluster: **no tasks with desired status `RUNNING`**.

Runtime OFF is therefore verified for this attempt. Network, ECR, ECS
cluster, persistent roles/logs, subnet groups, application secrets,
SQS/DLQ and publisher foundations remain, as do the separate website and
Cognito resources. Retained resources can still incur costs; this is not
evidence of zero account cost. No final bill or post-session credit balance
was reported.

After cleanup, the operator repaired only the parameter-group ARN in the
existing `CacheReferences` statement: `parametergroup:default.valkey7`
became `parametergroup:*`. That statement still allows only
`elasticache:CreateReplicationGroup`; the exact replication-group scope,
subnet-group/generated-cluster references, existing cache actions, and
isolated RDS metadata-read repair were retained. No policy version number
is asserted here.

An initial verifier incorrectly expected four top-level evaluation rows
and stopped on the ARN template `${ResourceType}:${ResourceName}`. AWS now
returns one aggregate `EvaluationResult` per action; concrete ARN decisions
must be read from `ResourceSpecificResults`, using `EvalResourceName` and
`EvalResourceDecision`. The corrected verifier checked the complete,
untruncated response and reported all four intended cache resource checks
allowed, with an unrelated replication-group ARN `implicitDeny`.

Those are policy-content and simulation results, not successful cache
creation, comprehensive provisioning authorization, or bootstrap/seed
execution evidence. The aborted window is closed. Keep runtime/queue/API
connection disabled; the repairs do not authorize another runtime-on apply
or reuse of either saved plan. A new live attempt requires a fresh reviewed
plan and an explicitly agreed purpose, time/cost window, and cleanup owner.

## 5. Future live phases — hold until separately approved

Do not execute this section now. A valid plan with errors elsewhere in its
output is not success. Resolve all holds relevant to the selected purpose,
review the full plan, and agree the stop time before proceeding.

| Phase | Exact action and acceptance condition | Stop condition |
| --- | --- | --- |
| A: Provision, not start | Review a fresh platform runtime-on plan with real staging identity/origin inputs. Use queue `disabled` for non-AI testing; use `sqs` only for an approved full test. Apply only after explicit approval. All created service desired counts must remain zero. Record the creation/start-of-cost time. | Unexpected replacements/destruction, paid topology changes, missing credentials, or failed/partial apply |
| B: Inspect resources | RDS `secure-cloudops-staging-db` and Valkey `secure-cloudops-staging-cache` are available in private subnets; RDS is not public. Private ALB is active. Read actual task ARNs and ALB identifiers from the existing outputs below. Confirm execution/task roles, secret references, approved image, and logs without printing secret values. | A public database/cache, wrong network/role/image, or unresolved partial apply |
| C: Bootstrap once | Use the guarded bootstrap procedure in the on-demand guide. Record the returned task ARN/client token. Inspect that same task's image/platform evidence. Require named container `database-bootstrap`, `STOPPED`, exit code `0`, and the success log before any service start. | Timeout, uncertain RunTask result, missing digest evidence, or nonzero/missing exit code; do not launch a duplicate task |
| C2: Identity test only | After successful bootstrap, use the dedicated restricted identity-seed task and the execution gate below if an identity test is explicitly approved. Keep services at zero. Require the same task's approved image/platform, named container `identity-seed`, `STOPPED`, exit code `0`, and sanitized completion evidence. An anonymous API liveness test may skip this phase. | Missing launch-command review, incorrect subject/role/secret, unresolved database grants, timeout, or nonzero/missing exit code; never substitute the administrator bootstrap task |
| D: Start API only | Inspect the exact API service at zero tasks and its expected task ARN. Deliberately scale it to one. Verify counts, task image/platform, and ALB target health before preparing the browser path. | Any deployment loop, dependency failure, wrong task/image, or unhealthy target |
| E: Browser/API path | In the frontend root only, prepare a VPC origin from that same active ALB, verify it is deployed, then attach the API route through a separately reviewed plan. After distribution deployment, verify the HTTPS `/api/v1/status` JSON response. The static website stays private behind CloudFront. | Wrong ALB identifiers, failed CloudFront deployment, incorrect HTTPS response, insecure entry workaround, or deadline reached |
| F: Full test only | Require completed C2 identity provisioning and provider/storage readiness. Start worker, then outbox publisher, one at a time after their gates. Perform one approved synthetic upload/processing/question/citation/audit test, including approved S3 storage/download checks. Record queue, database state, and application evidence; a worker log alone does not prove SQS delivery. | Provider/storage/permission failures, unexpected DLQ growth, failed authorization/citation, or repeated retries |
| G: Stop and remove | Execute section 9 even after a failed test. Stop task counts, detach/delete the API VPC origin, then review runtime removal. Verify absence and remaining costs. | Uncertain service/task status or still-attached CloudFront origin: investigate rather than deleting dependencies blindly |

An explicitly approved database/identity-only session can stop after C2
and proceed directly to shutdown without starting an application service.
The current runtime switch still provisions RDS, Valkey, and the ALB in
that case; it is not a database-only cost switch.

### Restricted identity-seed execution gate — future, not launch approval

These are the required ordering and acceptance checks. The exact bounded
PowerShell launch/observation commands still need a separate review in
chat before a paid session; this checklist is not permission to improvise
or execute a `RunTask` command now.

1. Require approved purpose, duration, credits, cleanup owner, full plan,
   provisioning/deletion permissions, and successful database bootstrap.
2. Read the actual registered `identity_seed_task_definition_arn`. Verify
   the exact account, region, family/revision, approved image mapping,
   Linux/X86_64 platform, container `identity-seed`, dedicated execution
   role, no application task role, restricted `securecloudops_app`
   database user, and only the application database-password secret.
   Check all staging guards. Never pass a master password to this task.
3. Select an owner-checked public staging subnet and a reviewed security
   group with PostgreSQL/HTTPS egress. A public IP supplies AWS-service
   egress because this VPC has no NAT/endpoints; it does not make RDS
   public or justify opening inbound database ports.
4. Confirm the exact intended staging user's `sub` privately. The sole
   container-command override is `python -m app.db.staging_identity --subject <operator-verified-sub>`; do not override environment,
   roles, image, or secrets. The subject is not a login credential, but
   task overrides/audit records can expose it to authorized operators;
   keep it out of shared outputs, source files, and Git.
5. Retain a unique client token and record the returned task ARN. Require
   exactly one task and zero failures. For timeout/uncertain results,
   inspect the same request/task before acting; do not generate a new
   token or blindly launch again, even though the seed is idempotent.
6. Inspect that same task. Require `STOPPED`, exactly one named seed
   container, exit code `0`, approved image/platform evidence, and a
   sanitized `Staging identity seed completed:` message and `role=manager`.
   A fresh seed should report all four creation flags as `True`; an exact,
   separately approved repeat should report all four as `False`. An
   unexpected mixture needs investigation, not acceptance or a blind rerun.
   A stopped task alone is not success.
   Keep any application-authentication acceptance test separate.
7. Record both bootstrap and identity-seed task ARNs for shutdown. Capture
   sanitized completion/failure evidence before runtime-off removes the
   seed's runtime-gated log group; its seven-day retention setting does
   not preserve the group after Terraform deletes it.

### Existing outputs: use these names, not invented service outputs

From the platform root, read `network_summary`, `ecs_cluster_summary`,
`ecs_role_arns`, `api_load_balancer`, `api_task_definition_arn`,
`worker_task_definition_arn`, `database_bootstrap_task_definition_arn`, and
`identity_seed_task_definition_arn`.
For SQS mode also read `document_queue_summary` and
`publisher_task_definition_arn`. Runtime task/ALB outputs are absent while
off; the publisher exists only when runtime is on **and** queue mode is
`sqs`. There are no Terraform service-name outputs.

All service tasks use public subnets with public IPs for outbound access
because no NAT gateway/endpoints are defined. Their security groups do not
therefore permit public browser entry. Database/cache stay private. Do not
open database ports or use a task public IP as the website's API address.

## 6. Future service start: one at a time, after bootstrap

| Service name | Task-definition output | Container name | Additional gate |
| --- | --- | --- | --- |
| `secure-cloudops-staging-api` | `api_task_definition_arn` | `api` | Database bootstrap succeeded; real Cognito/origin configuration |
| `secure-cloudops-staging-worker` | `worker_task_definition_arn` | `worker` | Full test approved; working embeddings, PostgreSQL/Redis, queue settings; tenant scope unset in SQS mode |
| `secure-cloudops-staging-publisher` | `publisher_task_definition_arn` | `publisher` | Full test approved; queue mode `sqs`; database grants/network and `sqs:SendMessage` verified |

Before each update, `aws ecs describe-services` must return exactly that
service, no failures, status `ACTIVE`, the expected task definition, and
desired/running/pending counts all zero. If it already has tasks, inspect
the existing session rather than launching or replacing tasks blindly.

Only after those checks and explicit live-session approval, the API start
operation is:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    if ((Read-Host 'Type START-STAGING-API only after the live-session gates are approved') -cne 'START-STAGING-API') {
        throw 'API start not confirmed.'
    }
    aws ecs update-service --cluster secure-cloudops-staging-cluster --service secure-cloudops-staging-api --desired-count 1 --region us-east-1 --profile securecloudops-dev --query 'service.{Name:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Task:taskDefinition}' --output json
    if ($LASTEXITCODE -ne 0) {
        throw 'API update result is uncertain. Inspect this service; do not repeat blindly.'
    }
}
```

For an approved full test only, start the worker after the API checks and
provider/queue gates pass:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    if ((Read-Host 'Type START-STAGING-WORKER only after the full-test provider and queue gates are approved') -cne 'START-STAGING-WORKER') {
        throw 'Worker start not confirmed.'
    }
    aws ecs update-service --cluster secure-cloudops-staging-cluster --service secure-cloudops-staging-worker --desired-count 1 --region us-east-1 --profile securecloudops-dev --query 'service.{Name:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Task:taskDefinition}' --output json
    if ($LASTEXITCODE -ne 0) {
        throw 'Worker update result is uncertain. Inspect this service; do not repeat blindly.'
    }
}
```

After the worker is verified, start the outbox publisher only if its
service exists and the approved full test uses SQS:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    if ((Read-Host 'Type START-STAGING-PUBLISHER only after the full-test SQS publisher gates are approved') -cne 'START-STAGING-PUBLISHER') {
        throw 'Publisher start not confirmed.'
    }
    aws ecs update-service --cluster secure-cloudops-staging-cluster --service secure-cloudops-staging-publisher --desired-count 1 --region us-east-1 --profile securecloudops-dev --query 'service.{Name:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Task:taskDefinition}' --output json
    if ($LASTEXITCODE -ne 0) {
        throw 'Publisher update result is uncertain. Inspect this service; do not repeat blindly.'
    }
}
```

Do not start either as part of the non-AI test. A disabled publisher
process can exit successfully without having published anything.

An ECS stable waiter is useful, but not sufficient:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $serviceToCheck = Read-Host 'Enter the exact service just started: secure-cloudops-staging-api, secure-cloudops-staging-worker, or secure-cloudops-staging-publisher'
    if ($serviceToCheck -cnotin @('secure-cloudops-staging-api', 'secure-cloudops-staging-worker', 'secure-cloudops-staging-publisher')) {
        throw 'Unexpected service name.'
    }
    aws ecs wait services-stable --cluster secure-cloudops-staging-cluster --services $serviceToCheck --region us-east-1 --profile securecloudops-dev
    $serviceWaitExitCode = $LASTEXITCODE
    aws ecs describe-services --cluster secure-cloudops-staging-cluster --services $serviceToCheck --region us-east-1 --profile securecloudops-dev --query '{Failures:failures,Services:services[].{Name:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Task:taskDefinition,Deployments:deployments,Events:events[:5]}}' --output json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the same service. Stop progressing.' }
    if ($serviceWaitExitCode -ne 0) { throw 'Service wait failed. Inspect the displayed service; do not start the next component.' }
}
```

The waiter can succeed at desired count zero. Require
desired `1`, running `1`, pending `0`, one completed expected deployment,
and the expected task definition before claiming startup success.

**Terraform warning:** all three services declare `desired_count=0` with
no `ignore_changes`. Manual scaling is temporary drift. A platform apply
during the session can scale services back to zero. Complete platform
configuration changes before service start; do not run an unrelated
platform apply mid-session. Frontend changes use the separate frontend root.

## 7. Prove the running task and API path

- Use `aws ecs list-tasks` scoped to the exact cluster and service, then
  `aws ecs describe-tasks` for the returned ARN(s). Require no API failures,
  the expected task definition, `RUNNING`, and the expected named container.
  Record its image reference, reported manifest digest, and Linux/X86_64
  task-definition platform. Compare with the approved manifest/platform
  mapping from section 1. Missing or ambiguous evidence is a hold.
- Task definitions currently do not declare an ECS container health check.
  Do not require a `HEALTHY` field that may legitimately be `UNKNOWN`, and
  do not treat `RUNNING` as application readiness.
- Read `api_load_balancer.target_group_arn` and use
  `aws elbv2 describe-target-health` for that exact group. The API target
  must be healthy; its configured check is `/ready` with HTTP `200`.
- `/health` and `/api/v1/status` prove liveness only. `/ready` probes
  PostgreSQL and Redis, not migrations/grants, identity, SQS, S3, or AI.
  Connectivity failures can surface as non-200 responses, including 500;
  do not assume only 503 indicates failure.
- After the API origin is attached and the distribution is deployed, use
  `<frontend_hosting.https_url>/api/v1/status` for the HTTPS liveness check.
  Only `/api/*` is routed to the API. `/health` and `/ready` on the
  CloudFront website domain go to the static S3 origin, not the API.
  Check the JSON body identifies `secure-cloudops-api`, not merely HTTP 200.
- Authenticated non-AI workspace/document reads require the separately
  provisioned staging subject and membership. A Cognito login alone does
  not grant application access. Do not bypass authorization to make a
  smoke test pass. Identity-session creation also writes an audit event;
  it is not a strictly read-only test.

### Read-only task evidence after each service start

Run this only for the service just started. It prints evidence for review;
its final command is not an automatic image/platform approval:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $taskService = Read-Host 'Enter the exact service just started: secure-cloudops-staging-api, secure-cloudops-staging-worker, or secure-cloudops-staging-publisher'
    if ($taskService -cnotin @('secure-cloudops-staging-api', 'secure-cloudops-staging-worker', 'secure-cloudops-staging-publisher')) {
        throw 'Unexpected service name.'
    }
    $taskListText = aws ecs list-tasks --cluster secure-cloudops-staging-cluster --service-name $taskService --desired-status RUNNING --region us-east-1 --profile securecloudops-dev --query taskArns --output json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot list this service task. Stop progressing.' }
    $taskArns = @(($taskListText -join "`n") | ConvertFrom-Json)
    if ($taskArns.Count -ne 1) { throw 'Expected exactly one service task. Inspect counts and deployments.' }
    $taskDetailsText = aws ecs describe-tasks --cluster secure-cloudops-staging-cluster --tasks $taskArns[0] --region us-east-1 --profile securecloudops-dev --query '{Failures:failures,Tasks:tasks[].{Arn:taskArn,Definition:taskDefinitionArn,Status:lastStatus,StopCode:stopCode,StoppedReason:stoppedReason,Containers:containers[].{Name:name,Image:image,Digest:imageDigest,Status:lastStatus,Exit:exitCode}}}' --output json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the selected task. Stop progressing.' }
    $taskDetails = ($taskDetailsText -join "`n") | ConvertFrom-Json
    if ($taskDetails.Failures.Count -ne 0 -or $taskDetails.Tasks.Count -ne 1) {
        throw 'Task inspection did not return exactly one task with no failures.'
    }
    $taskDetailsText
    $registeredDefinition = $taskDetails.Tasks[0].Definition
    if ($registeredDefinition -notlike 'arn:aws:ecs:us-east-1:291667884598:task-definition/secure-cloudops-staging-*:*') {
        throw 'Unexpected task definition scope.'
    }
    aws ecs describe-task-definition --task-definition $registeredDefinition --region us-east-1 --profile securecloudops-dev --query 'taskDefinition.{Arn:taskDefinitionArn,Platform:runtimePlatform,Containers:containerDefinitions[].{Name:name,Image:image}}' --output json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the registered task platform/image.' }
}
```

Require an empty `Failures` array and the task/container/platform checks
above, not just AWS CLI exit code zero. The final command displays the
registered platform/image; compare its ARN against the exact Terraform
task-definition output in the service table. Do not infer a successful
container from a matching tag alone.

### Read-only ALB and HTTPS checks after the API is running

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $albText = terraform -chdir=infra\terraform\environments\staging output -json api_load_balancer
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read the runtime ALB output.' }
    $alb = ($albText -join "`n") | ConvertFrom-Json
    if ($alb.target_group_arn -notlike 'arn:aws:elasticloadbalancing:us-east-1:291667884598:targetgroup/secure-cloudops-staging-api-tg/*') {
        throw 'Unexpected or missing staging API target group.'
    }
    aws elbv2 describe-target-health --target-group-arn $alb.target_group_arn --region us-east-1 --profile securecloudops-dev --output json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect API target health.' }
}
```

Require a healthy target matching the selected API task; an empty group is
not success. Only after that and approved CloudFront attachment:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $hostingText = terraform -chdir=infra\terraform\environments\staging-frontend output -json frontend_hosting
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read the staging frontend output.' }
    $hosting = ($hostingText -join "`n") | ConvertFrom-Json
    if ($hosting.https_url -cnotmatch '^https://[a-z0-9]+\.cloudfront\.net$') {
        throw 'Unexpected staging HTTPS origin.'
    }
    $apiStatus = Invoke-RestMethod -Uri ($hosting.https_url + '/api/v1/status') -Method Get -TimeoutSec 30
    if ($apiStatus.status -ne 'ok' -or $apiStatus.service -ne 'secure-cloudops-api') {
        throw 'HTTPS response was not the expected API liveness payload.'
    }
    Write-Host 'PASS: API HTTPS liveness only; not an AI, identity, or ingestion result.'
}
```

## 8. Observation, timeout, and failure recovery

Inspect the scoped ECS service events/stopped tasks and CloudWatch groups
`/ecs/secure-cloudops-staging/{api,worker,publisher,database-bootstrap,identity-seed}`.
Record task stop codes and safe error categories; inspect/sanitize logs
before sharing. Never paste JWTs, AWS credentials, secret values, or raw
document contents into logs, issues, or this runbook.

An idle worker or empty queue is not proof of ingestion: demonstrate one
synthetic document's committed intent, publication, consumption, processing,
and persisted result. Record DLQ counts without purging or replaying.
The worker retains a database sweep, so a processed document alone does
not prove the SQS path was used.

At any failed gate or agreed deadline, stop starting additional components,
inspect the same returned task/service, and enter section 9. ECS services
can keep replacing failed tasks until deliberately scaled down. Do not
leave a failed session unattended or repeatedly force new deployments.
If AWS access is lost, restore operator login, inspect actual state, and
finish cleanup; absence of terminal access is not proof resources stopped.
Closing PowerShell, pressing Ctrl+C, or logging out does not stop AWS
tasks, databases, caches, or load balancers. Resume scoped inspection and
cleanup rather than assuming the interrupted command shut them down.

This is the first live deployment: no earlier cloud revision is yet a
verified rollback target. The safe abort is stop/cleanup, not an automatic
image rollback or Alembic downgrade. A future rollback needs a separately
verified image and schema-compatibility plan. A failed Terraform apply is
not automatically rolled back; refresh/review a new plan before acting.

## 9. Future shutdown: perform even when a test failed

1. Stop browser requests and uploads. Record whether any synthetic work is
   unfinished and explicitly accept its disposal before database removal.
2. Deliberately scale each service that actually exists to zero: API,
   then publisher (SQS full session only), then worker. Use the exact
   service table; never attempt to start a missing service to stop it.
   The approved API stop operation is:

   ```powershell
   & {
       $ErrorActionPreference = 'Stop'
       if ((Read-Host 'Type STOP-STAGING-API to stop the staging API service') -cne 'STOP-STAGING-API') {
           throw 'API stop not confirmed.'
       }
       aws ecs update-service --cluster secure-cloudops-staging-cluster --service secure-cloudops-staging-api --desired-count 0 --region us-east-1 --profile securecloudops-dev --query 'service.{Name:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount}' --output json
       if ($LASTEXITCODE -ne 0) {
           throw 'API stop result is uncertain. Inspect this service before proceeding.'
       }
   }
   ```

   For the SQS full-test publisher, only if that service exists:

   ```powershell
   & {
       $ErrorActionPreference = 'Stop'
       if ((Read-Host 'Type STOP-STAGING-PUBLISHER to stop the staging outbox publisher service') -cne 'STOP-STAGING-PUBLISHER') {
           throw 'Publisher stop not confirmed.'
       }
       aws ecs update-service --cluster secure-cloudops-staging-cluster --service secure-cloudops-staging-publisher --desired-count 0 --region us-east-1 --profile securecloudops-dev --query 'service.{Name:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount}' --output json
       if ($LASTEXITCODE -ne 0) {
           throw 'Publisher stop result is uncertain. Inspect this service before proceeding.'
       }
   }
   ```

   For the worker, only if that service exists:

   ```powershell
   & {
       $ErrorActionPreference = 'Stop'
       if ((Read-Host 'Type STOP-STAGING-WORKER to stop the staging worker service') -cne 'STOP-STAGING-WORKER') {
           throw 'Worker stop not confirmed.'
       }
       aws ecs update-service --cluster secure-cloudops-staging-cluster --service secure-cloudops-staging-worker --desired-count 0 --region us-east-1 --profile securecloudops-dev --query 'service.{Name:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount}' --output json
       if ($LASTEXITCODE -ne 0) {
           throw 'Worker stop result is uncertain. Inspect this service before proceeding.'
       }
   }
   ```

3. Inspect each selected service until desired/running/pending are all
   zero, and verify its tracked tasks stopped. Also inspect the recorded
   standalone database-bootstrap and identity-seed tasks: scaling services
   does not stop a standalone RunTask. For either task still running,
   obtain explicit approval to stop that exact recorded ARN; do not launch
   a replacement. Save sanitized task-exit and log evidence before deleting
   the runtime-gated seed log group or its database dependencies.
4. If attached, change CloudFront API mode `attached` to `prepared`,
   review/apply the frontend-only change, and verify the distribution is
   `Deployed`. Then change `prepared` to `disabled`, review/apply, and
   verify the VPC origin is deleted. If already disabled, do not attach it
   just to exercise shutdown. **Do not delete the ALB first.**
5. Review a fresh platform plan with `runtime_enabled=false`. Removal is
   intentional permanent loss of the disposable database/cache; current
   RDS configuration skips the final snapshot and deletes automated backups.
   Expected removals include runtime RDS/Valkey, API/worker and optional
   publisher services/tasks, bootstrap task and runtime-only policies,
   identity-seed task/execution role/policy/log group,
   private ALB/listener/target group and their runtime security resources.
   Preserve network, ECR, ECS cluster, persistent roles/secrets/queues,
   static website, and staging Cognito. Stop on unrelated destruction.
6. Only after explicit acceptance of the reviewed data loss, apply the
   runtime-off change using the on-demand guide; never `terraform destroy`
   either root or use `-auto-approve`. Verify removals using a new plan and
   scoped AWS service checks. Off is not zero cost: retained secrets,
   storage/images/logs/queues/frontend resources may still incur charges.
7. Persistent SQS/DLQ messages can outlive the disposable database. Record
   their remaining counts and review their next-session handling. Do not
   purge/replay queues or delete retained data as an implicit cleanup step.

## 10. Evidence required before calling a session successful

Record the approved purpose, source/image identifiers and manifest mapping,
start/stop times, real non-sensitive outputs, bootstrap and any seed exit results,
service counts/tasks, ALB health, HTTPS response, and any full-test case IDs.
Record failed/skipped gates honestly. Preserve the final runtime-off plan
and deletion checks, with any residual costs/resources noted. Do not store
Terraform state/plan files or credentials in Git.

Documentation review, a valid plan, liveness, and an idle worker are not
V0.4 release evidence. Full release still needs the approved browser-to-
answer path, authorization/citations/auditing, failure recovery, and tested
cleanup/rollback boundaries.

## Primary references

- [IAM evaluation-result structure](https://docs.aws.amazon.com/IAM/latest/APIReference/API_EvaluationResult.html): action aggregates and per-resource results; top-level ARN templates are not customer resource ARNs.
- [RDS provider 6.66.0 implementation](https://github.com/hashicorp/terraform-provider-aws/blob/v6.66.0/internal/service/rds/instance.go): generated resource IDs and filtered post-create metadata reads.
- [ElastiCache provider 6.66.0 implementation](https://github.com/hashicorp/terraform-provider-aws/blob/v6.66.0/internal/service/elasticache/replication_group.go): parameter-group names are sent only when configured.
- [ECS service stability waiter](https://docs.aws.amazon.com/cli/latest/reference/ecs/wait/services-stable.html): stability checks desired/running counts, not full application behavior.
- [ECS task inspection](https://docs.aws.amazon.com/cli/latest/reference/ecs/describe-tasks.html): task/container status, stop details, and manifest digest.
- [IAM principal simulation](https://docs.aws.amazon.com/cli/latest/reference/iam/simulate-principal-policy.html): simulations do not launch tasks and are not substitutes for service-side verification.
- [CloudWatch log reads](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_GetLogEvents.html): event time ranges, empty responses, and lookup errors.
- [ECS image resolution](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html#deployment-container-image-stability): tag resolution and zero-desired-count limitations.
- [ECR manifest lists](https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-push-multi-architecture-image.html): top-level lists can reference platform-specific images.
- [CloudFront VPC origins](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html): active private origins and distribution association/removal requirements.
