# Controlled staging-session runbook

Prepared on 16 October 2026 for `codex/v04-aws-platform`.

**Status: documentation/preflight only. No live session is approved by this
document, and these service-start/shutdown procedures have not been tested
on AWS. Do not execute the future live phases yet.** Keep
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
| Verified commit tag | `998e4bfb58dd9c3f6463d4de7ae61b4db8a25235` |
| Verified top-level registry digest | `sha256:137956eac847118421725ce246b46bcb5466c90a899e3eb4682a15ac78923d20` |

[Publication evidence](api-image-security.md#api-image-publication--verified-16-october-2026)
records the successful CI run and operator's ECR lookup. The API, worker,
database bootstrap, and outbox publisher share `local.staging_api_image_tag`
in `ecs_api_task.tf`. A later documentation or Terraform-only commit does
not require rebuilding an unchanged image.

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
| Planning/preflight (current) | Read configuration, validate, inspect identity/image metadata, and review plans | Apply, create runtime resources, scale services up, attach the API origin, upload test data |
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
- **Browser configuration:** Resolve the dedicated staging Cognito and
  frontend outputs, real callback/logout addresses, frontend build-time
  settings, and API `staging_frontend_origin`. Source defaults being blank
  does not mean a staging pool is absent, and deployed Cognito resources
  do not prove browser sign-in or application membership works.
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
aws ecr describe-images --registry-id 291667884598 --repository-name secure-cloudops-staging/api --image-ids imageTag=998e4bfb58dd9c3f6463d4de7ae61b4db8a25235 --region us-east-1 --profile securecloudops-dev --query 'imageDetails[0].{Digest:imageDigest,MediaType:imageManifestMediaType,Tags:imageTags}' --output json
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

## 5. Future live phases — hold until separately approved

Do not execute this section now. A valid plan with errors elsewhere in its
output is not success. Resolve all holds relevant to the selected purpose,
review the full plan, and agree the stop time before proceeding.

| Phase | Exact action and acceptance condition | Stop condition |
| --- | --- | --- |
| A: Provision, not start | Review a fresh platform runtime-on plan with real staging identity/origin inputs. Use queue `disabled` for non-AI testing; use `sqs` only for an approved full test. Apply only after explicit approval. All created service desired counts must remain zero. Record the creation/start-of-cost time. | Unexpected replacements/destruction, paid topology changes, missing credentials, or failed/partial apply |
| B: Inspect resources | RDS `secure-cloudops-staging-db` and Valkey `secure-cloudops-staging-cache` are available in private subnets; RDS is not public. Private ALB is active. Read actual task ARNs and ALB identifiers from the existing outputs below. Confirm execution/task roles, secret references, approved image, and logs without printing secret values. | A public database/cache, wrong network/role/image, or unresolved partial apply |
| C: Bootstrap once | Use the guarded bootstrap procedure in the on-demand guide. Record the returned task ARN/client token. Inspect that same task's image/platform evidence. Require named container `database-bootstrap`, `STOPPED`, exit code `0`, and the success log before any service start. | Timeout, uncertain RunTask result, missing digest evidence, or nonzero/missing exit code; do not launch a duplicate task |
| D: Start API only | Inspect the exact API service at zero tasks and its expected task ARN. Deliberately scale it to one. Verify counts, task image/platform, and ALB target health before preparing the browser path. | Any deployment loop, dependency failure, wrong task/image, or unhealthy target |
| E: Browser/API path | In the frontend root only, prepare a VPC origin from that same active ALB, verify it is deployed, then attach the API route through a separately reviewed plan. After distribution deployment, verify the HTTPS `/api/v1/status` JSON response. The static website stays private behind CloudFront. | Wrong ALB identifiers, failed CloudFront deployment, incorrect HTTPS response, insecure entry workaround, or deadline reached |
| F: Full test only | Complete approved synthetic tenant/user/membership provisioning and provider/storage readiness. Start worker, then outbox publisher, one at a time after their gates. Perform one approved synthetic upload/processing/question/citation/audit test, including approved S3 storage/download checks. Record queue, database state, and application evidence; a worker log alone does not prove SQS delivery. | Provider/storage/permission failures, unexpected DLQ growth, failed authorization/citation, or repeated retries |
| G: Stop and remove | Execute section 9 even after a failed test. Stop task counts, detach/delete the API VPC origin, then review runtime removal. Verify absence and remaining costs. | Uncertain service/task status or still-attached CloudFront origin: investigate rather than deleting dependencies blindly |

### Existing outputs: use these names, not invented service outputs

From the platform root, read `network_summary`, `ecs_cluster_summary`,
`ecs_role_arns`, `api_load_balancer`, `api_task_definition_arn`,
`worker_task_definition_arn`, and `database_bootstrap_task_definition_arn`.
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
`/ecs/secure-cloudops-staging/{api,worker,publisher,database-bootstrap}`.
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
   standalone bootstrap task: scaling services does not stop a standalone
   RunTask. If it is unexpectedly still running, obtain explicit approval
   to stop that exact task ARN; do not launch another bootstrap.
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
start/stop times, real non-sensitive outputs, bootstrap exit result,
service counts/tasks, ALB health, HTTPS response, and any full-test case IDs.
Record failed/skipped gates honestly. Preserve the final runtime-off plan
and deletion checks, with any residual costs/resources noted. Do not store
Terraform state/plan files or credentials in Git.

Documentation review, a valid plan, liveness, and an idle worker are not
V0.4 release evidence. Full release still needs the approved browser-to-
answer path, authorization/citations/auditing, failure recovery, and tested
cleanup/rollback boundaries.

## Primary references

- [ECS service stability waiter](https://docs.aws.amazon.com/cli/latest/reference/ecs/wait/services-stable.html): stability checks desired/running counts, not full application behavior.
- [ECS task inspection](https://docs.aws.amazon.com/cli/latest/reference/ecs/describe-tasks.html): task/container status, stop details, and manifest digest.
- [ECS image resolution](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html#deployment-container-image-stability): tag resolution and zero-desired-count limitations.
- [ECR manifest lists](https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-push-multi-architecture-image.html): top-level lists can reference platform-specific images.
- [CloudFront VPC origins](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html): active private origins and distribution association/removal requirements.
