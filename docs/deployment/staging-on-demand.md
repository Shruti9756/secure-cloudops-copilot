# Staging on-demand runtime

This procedure is for the **staging** Terraform environment and **synthetic data only**. It is not a pause button: turning the runtime off deletes the staging PostgreSQL database and Valkey cache.

The persistent network, ECR repositories, ECS cluster, and two application secrets remain when the runtime is off. Therefore, off does not mean zero AWS cost.

The static website is managed separately by `infra/terraform/environments/staging-frontend`, with its own Terraform state at `states/staging/frontend.tfstate`. The website's private S3 bucket and CloudFront distribution are **not** controlled by `runtime_enabled`; switching the platform runtime off does not remove them. Run website plans from the `staging-frontend` root, never from this platform root when the intention is to change only the website.

## Readiness gate for a full staging test

Keep `runtime_enabled=false` until there is a specific test session and a reviewed way to start, observe, and stop every billable runtime component. The [controlled-session runbook](staging-session-runbook.md) records the current holds, exact service names, start/verification order, and failure/shutdown criteria. It is prepared documentation, not live-tested deployment evidence or approval to start a session.

A Terraform task definition is only a container recipe. API, worker, and the optional SQS outbox publisher all have `desired_count = 0`; enabling the runtime alone starts none of them. The publisher is created only when runtime is enabled and queue mode is `sqs`.

Before a full browser-to-answer test, review these dependencies in order:

1. **Website:** Confirm that the separate frontend state contains a successfully created CloudFront distribution and its private-bucket read policy. Build the static export with staging browser settings, publish it, and confirm its HTTPS URL and `auth/callback.html` route. A bucket and origin access control alone do not make the website available.
2. **API entry:** The platform now defines a runtime-gated private Application Load Balancer, and the separate frontend root defines a disabled CloudFront VPC-origin connection. Verify the actual active ALB, origin, and HTTPS path during an approved session; definitions alone are not a deployed API. Do not rely on a task's public IP as the browser entry point.
3. **Identity and browser configuration:** Use a dedicated staging Cognito pool and app client, not the development identifiers. Match its callback/logout URLs, the frontend's build-time `NEXT_PUBLIC_*` values, and the API's allowed browser origin to the actual staging HTTPS addresses.
4. **AI and ingestion:** Select cloud-usable embedding and chat providers for the API and worker, confirm required model authorization, and make both sides use the same embedding model. The worker task and service are defined but start at zero tasks; review how to start and stop the worker before testing uploads.
5. **Controlled session:** Review database bootstrap, API and worker start/stop, a smoke test, and the runtime-off plan. Confirm that all staging data is disposable, because switching the runtime off deletes the database and cache.

This checklist is a design gate, not an instruction to apply Terraform or start services. A partial AWS apply does not satisfy a step merely because some supporting resources exist; verify the actual outputs and a fresh plan first.

### Local preflight findings

These findings describe the current repository configuration, not the status of an AWS deployment. Resolve and verify each one before a full browser-to-answer staging test:

| Gate | Current configuration | What must be verified |
| --- | --- | --- |
| Staging sign-in | The dedicated staging Cognito pool/client were previously deployed and verified. Platform input defaults remain blank, and the API refuses an on-mode plan without real issuer/client values. | Read `staging_identity` from the frontend root; match browser callbacks/logout and API inputs. Separately provision the synthetic tenant/user/membership. Deployed Cognito alone does not prove application access. |
| Browser-to-API connection | A private runtime-gated ALB and disabled CloudFront API connection are defined. `ecs_api_task.tf` supplies `CORS_ALLOWED_ORIGINS` from `staging_frontend_origin`. | Verify the real frontend origin, healthy ALB `/ready` target, and attached `/api/*` HTTPS routing. A public task IP is not the browser entry point. |
| Embedding and answers | The API and worker task definitions do not select an embedding provider, so both default to Ollama at `127.0.0.1`. The API chat provider also uses Ollama. No staging Ollama service is defined. | The API and worker use the same reachable embedding model, answer generation uses a reachable chat model, and any required model permissions are confirmed before starting tasks. |
| Application seed/provisioning | Database bootstrap applies migrations and restricted-role grants, not tenants/users/memberships. The image does not package existing `scripts/` or demo-data files. | Review an explicit synthetic-data and identity provisioning mechanism before authenticated/ingestion tests. Do not invent unshipped script entry points. |
| Private document storage | The application defaults to a disabled document-storage backend; the staging API task supplies no S3 document-store settings. | Review a private staging document bucket, scoped task permissions, and redacted storage/authorized download evidence. The static frontend bucket must not be reused for uploaded documents. |
| Controlled runtime | API, worker, and optional publisher desired counts are zero, with no lifecycle rule ignoring manual count changes. | Bootstrap first; verify each service/task and functional gate separately. A platform apply can reset a manually started service to zero. Complete the controlled-session review before a short test. |

Do not change these to development URLs or placeholder identifiers merely to make a plan pass. Model access and the browser path remain separate checks even after Terraform validation succeeds.

## Before any Terraform apply

From `C:\Users\Shru\Documents\AI+AWS`:

```powershell
aws sts get-caller-identity --profile securecloudops-dev --query Account --output text
terraform -chdir=infra\terraform\environments\staging validate
```

The account must be `291667884598`. Stop if it differs or validation fails. Check available AWS credits and the budget dashboard. A budget alert is a warning, not an automatic spending stop.

Never use `-auto-approve` or `terraform destroy` for this staging Terraform root.

## First-time supporting setup

This creates supporting resources **without** creating the RDS instance or Valkey node:

```powershell
terraform -chdir=infra\terraform\environments\staging plan -input=false -var="runtime_enabled=false"
```

The off-mode plan reviewed for the verified-image handoff on 16 October 2026 showed **25 adds, 1 change, 0 destroys**. These were pending supporting resources, including publisher roles/rules, SQS, and two application secrets; the one update added the publisher rule to database security-group ownership. No RDS instance, Valkey replication group, ECS service/task definition, or ALB creation was proposed. Read names, not a fixed count. Planning does not apply the changes, and an off-mode apply can still create resources with ongoing cost.

Only after deciding to create those resources, run:

```powershell
terraform -chdir=infra\terraform\environments\staging apply -var="runtime_enabled=false"
```

Terraform will show a **fresh plan** and ask for approval. Check it again before typing `yes`. If it differs from what you expected, type `no` and stop.

## Start a planned test session

**Hold for now:** Do not run this section until real staging identity/origin inputs and the [controlled-session gates](staging-session-runbook.md) are reviewed for an explicitly approved purpose and cost window. Full ingestion/answer testing additionally needs working providers and an approved synthetic seed/provisioning path. Turning runtime on creates RDS, Valkey, and the private ALB while services remain at zero tasks; charges can begin before the API is started.

First review:

```powershell
terraform -chdir=infra\terraform\environments\staging plan -input=false -var="runtime_enabled=true"
```

Until the staging Cognito issuer and app client ID are configured, an on-mode plan must fail the API task's safety check. A `Plan: ...` line alongside that error is not a successful plan. Do not insert development or placeholder values to make it pass. After a real staging pool and client are configured, review a complete plan by resource name rather than relying on a fixed count. It should include RDS, Valkey, the API and worker task definitions and services, and their required policies, with no unexpected destroys. RDS and Valkey can incur charges while they exist.

Only when ready for a cloud test, run:

```powershell
terraform -chdir=infra\terraform\environments\staging apply -var="runtime_enabled=true"
```

Review the fresh plan before typing `yes`. Record when the database and cache are created.

**This does not start the application.** API, worker, and optional publisher services have `desired_count = 0`. Bootstrap and deliberate service starts are separate phases in the controlled-session runbook. Do not improvise them or treat a zero-task stable service as a successful application start.

## Database bootstrap — future test session

**Do not run this yet.** First, the reviewed `runtime_enabled=true` apply must create RDS and the bootstrap task definition. The selected controlled-session purpose, image/platform checks, API-start, and shutdown procedures must also be reviewed. Terraform registers this one-off task but never runs it automatically. The commands below do not themselves enforce every session gate: inspect the registered bootstrap task's approved image, roles, and network before launching, then check the returned task's manifest/platform evidence before accepting success.

The task applies database migrations and creates the restricted `securecloudops_app` database role. Run it in a public staging subnet with a public IP because this VPC has no NAT gateway or VPC endpoints. The database itself remains private. The AWS identity running it needs `ecs:RunTask`, `ecs:DescribeTasks`, and `iam:PassRole` for the bootstrap execution role.

```powershell
Set-Location -LiteralPath 'C:\Users\Shru\Documents\AI+AWS'

$account = aws sts get-caller-identity --profile securecloudops-dev --query Account --output text
if ($LASTEXITCODE -ne 0 -or $account -ne '291667884598') {
    throw 'AWS identity check failed or account is wrong. Stop.'
}

$networkText = terraform -chdir=infra\terraform\environments\staging output -json network_summary
if ($LASTEXITCODE -ne 0) { throw 'Cannot read staging network output.' }
$network = ($networkText -join "`n") | ConvertFrom-Json

$clusterText = terraform -chdir=infra\terraform\environments\staging output -json ecs_cluster_summary
if ($LASTEXITCODE -ne 0) { throw 'Cannot read staging cluster output.' }
$cluster = ($clusterText -join "`n") | ConvertFrom-Json

$definitionText = terraform -chdir=infra\terraform\environments\staging output -raw database_bootstrap_task_definition_arn
if ($LASTEXITCODE -ne 0) { throw 'Bootstrap task definition is unavailable.' }
$definition = ($definitionText -join '').Trim()

if ($definition -notlike 'arn:aws:ecs:us-east-1:291667884598:task-definition/secure-cloudops-staging-database-bootstrap:*') {
    throw 'Unexpected bootstrap task definition. Stop.'
}
if ($cluster.cluster_arn -ne 'arn:aws:ecs:us-east-1:291667884598:cluster/secure-cloudops-staging-cluster') {
    throw 'Unexpected ECS cluster. Stop.'
}

$subnet = $network.public_subnet_ids[0]
$securityGroup = $network.security_group_ids.api
if (-not $subnet -or -not $securityGroup) {
    throw 'Public subnet or API security group is missing.'
}

$networkArgument = "awsvpcConfiguration={subnets=[$subnet],securityGroups=[$securityGroup],assignPublicIp=ENABLED}"
$clientToken = [guid]::NewGuid().ToString('N')

$runText = aws ecs run-task `
    --cluster $cluster.cluster_arn `
    --task-definition $definition `
    --launch-type FARGATE `
    --count 1 `
    --network-configuration $networkArgument `
    --client-token $clientToken `
    --region us-east-1 `
    --profile securecloudops-dev `
    --output json

if ($LASTEXITCODE -ne 0) {
    throw 'RunTask result is uncertain. Inspect ECS; do not rerun blindly.'
}
$run = ($runText -join "`n") | ConvertFrom-Json
if ($run.failures.Count -ne 0 -or $run.tasks.Count -ne 1) {
    throw 'RunTask did not return exactly one task with zero failures.'
}

$taskArn = $run.tasks[0].taskArn
Write-Host "Bootstrap task ARN: $taskArn"

aws ecs wait tasks-stopped `
    --cluster $cluster.cluster_arn `
    --tasks $taskArn `
    --region us-east-1 `
    --profile securecloudops-dev
$waitExitCode = $LASTEXITCODE

$detailsText = aws ecs describe-tasks `
    --cluster $cluster.cluster_arn `
    --tasks $taskArn `
    --region us-east-1 `
    --profile securecloudops-dev `
    --output json
if ($LASTEXITCODE -ne 0) {
    throw 'Cannot inspect the task. Do not launch another.'
}

$details = ($detailsText -join "`n") | ConvertFrom-Json
if ($details.failures.Count -ne 0 -or $details.tasks.Count -ne 1) {
    throw 'Task inspection failed. Do not launch another.'
}
$task = $details.tasks[0]
$container = @($task.containers | Where-Object { $_.name -eq 'database-bootstrap' })

if ($waitExitCode -ne 0) {
    throw "Wait did not finish; current status is $($task.lastStatus). Inspect this same task."
}
if ($task.lastStatus -ne 'STOPPED' -or $container.Count -ne 1 -or $container[0].exitCode -ne 0) {
    throw 'Bootstrap failed. Inspect its ECS task and CloudWatch logs; do not start the API.'
}

Write-Host 'PASS: database migrations and restricted application role completed.'
```

A task being `STOPPED` only means it finished; require the named container's **exit code `0`**, expected image/task/platform evidence, and the bootstrap success log. A failed wait or missing result is not permission to launch another task. Bootstrap does not seed application users/workspaces or prove AI readiness.

## End a test session

### CloudFront API connection shutdown gate

Do not delete the runtime ALB while CloudFront still uses its VPC origin.

The separate `staging-frontend` root controls `staging_api_connection_mode`:

- `disabled`: no API VPC origin and no API distribution routing.
- `prepared`: the API VPC origin exists but is detached from the distribution.
- `attached`: the distribution routes `/api/*` through that VPC origin.

Keep this mode `disabled` until a reviewed test session. During a future session,
use the real ARN and DNS name from the same active staging API ALB.

If the connection is attached, shutdown must follow this order:

1. Change the frontend mode from `attached` to `prepared`. Review and apply
   that frontend-only change, then verify the distribution is `Deployed`.
2. Change the frontend mode from `prepared` to `disabled`. Review and apply
   that frontend-only change, then verify the VPC origin has been deleted.
3. Only then review and apply the platform's `runtime_enabled=false` plan.

If the connection is already disabled, no CloudFront detachment is needed.

Never change the VPC origin's ALB ARN while it is attached. Never use
`terraform destroy` on the frontend root to perform this shutdown.
The website and staging Cognito must remain intact.

The instructions below are not permission to start a session before its
bootstrap, service-start, observation, and shutdown steps are reviewed.
First stop new requests and explicitly scale each existing selected service
to zero, verify desired/running/pending counts and tracked tasks, and inspect
the separate bootstrap task. The controlled-session runbook records this
order, the optional publisher condition, and uncertain-result handling.

First confirm that all staging data is disposable. The current RDS settings skip a final snapshot and delete automated backups. Assume that turning the runtime off permanently loses its database data.

Review the removal:

```powershell
terraform -chdir=infra\terraform\environments\staging plan -input=false -var="runtime_enabled=false"
```

With the current design, expect removal of the RDS instance, Valkey replication group, API/worker and optional publisher services/task definitions, bootstrap task definition, runtime-only secret-read policies, private API ALB/listener/target group, and their runtime security resources. Stop if Terraform also proposes deleting the network, ECR repositories, ECS cluster, persistent roles/application secrets, SQS/DLQ, static frontend, or staging Cognito. Persistent queue messages may outlive the disposable database; review their handling separately and do not purge/replay as an implicit cleanup step.

Only after reviewing and accepting that data loss, run:

```powershell
terraform -chdir=infra\terraform\environments\staging apply -var="runtime_enabled=false"
```

Review the fresh plan again before typing `yes`. Then check:

```powershell
terraform -chdir=infra\terraform\environments\staging state list
terraform -chdir=infra\terraform\environments\staging plan -input=false -var="runtime_enabled=false"
```

The runtime resources should be absent from state, and the off plan should show no further changes. Record when deletion finished.

If an apply fails partway through, **do not assume Terraform rolled it back**. Inspect the error and run a new plan before taking another action.
