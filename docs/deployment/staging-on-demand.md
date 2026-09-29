# Staging on-demand runtime

This procedure is for the **staging** Terraform environment and **synthetic data only**. It is not a pause button: turning the runtime off deletes the staging PostgreSQL database and Valkey cache.

The persistent network, ECR repositories, ECS cluster, and two application secrets remain when the runtime is off. Therefore, off does not mean zero AWS cost.

The static website is managed separately by `infra/terraform/environments/staging-frontend`, with its own Terraform state at `states/staging/frontend.tfstate`. The website's private S3 bucket and CloudFront distribution are **not** controlled by `runtime_enabled`; switching the platform runtime off does not remove them. Run website plans from the `staging-frontend` root, never from this platform root when the intention is to change only the website.

## Readiness gate for a full staging test

Keep `runtime_enabled=false` until there is a specific test session and a reviewed way to start, observe, and stop every billable runtime component. A Terraform task definition is only a container recipe; both the API and worker services have `desired_count = 0`, so enabling the runtime alone will not start either container.

Before a full browser-to-answer test, review these dependencies in order:

1. **Website:** Confirm that the separate frontend state contains a successfully created CloudFront distribution and its private-bucket read policy. Build the static export with staging browser settings, publish it, and confirm its HTTPS URL and `auth/callback.html` route. A bucket and origin access control alone do not make the website available.
2. **API entry:** Provide a reviewed HTTPS entry point for the API. The API security group allows requests from the load-balancer security group, but this configuration does not yet create an Application Load Balancer or a public API URL. Do not rely on the task's public IP as the browser entry point.
3. **Identity and browser configuration:** Use a dedicated staging Cognito pool and app client, not the development identifiers. Match its callback/logout URLs, the frontend's build-time `NEXT_PUBLIC_*` values, and the API's allowed browser origin to the actual staging HTTPS addresses.
4. **AI and ingestion:** Select cloud-usable embedding and chat providers for the API and worker, confirm required model authorization, and make both sides use the same embedding model. The worker task and service are defined but start at zero tasks; review how to start and stop the worker before testing uploads.
5. **Controlled session:** Review database bootstrap, API and worker start/stop, a smoke test, and the runtime-off plan. Confirm that all staging data is disposable, because switching the runtime off deletes the database and cache.

This checklist is a design gate, not an instruction to apply Terraform or start services. A partial AWS apply does not satisfy a step merely because some supporting resources exist; verify the actual outputs and a fresh plan first.

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

The last reviewed off-mode plan showed **11 adds, 0 changes, 0 destroys**. The count can change after an apply or code update, so read the resource names rather than treating 11 as a target. The additions include two Secrets Manager secrets, which can have ongoing cost.

Only after deciding to create those resources, run:

```powershell
terraform -chdir=infra\terraform\environments\staging apply -var="runtime_enabled=false"
```

Terraform will show a **fresh plan** and ask for approval. Check it again before typing `yes`. If it differs from what you expected, type `no` and stop.

## Start a planned test session

**Hold for now:** Do not run this section until staging Cognito is configured and the separate database-bootstrap, API/worker-start, and session-shutdown steps are documented and reviewed. Turning the runtime on creates RDS and Valkey while the API and worker remain stopped.

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

**This does not start the application.** The API and worker services have `desired_count = 0`. Running the one-off database bootstrap task and then starting the API and worker require separate reviewed instructions; do not improvise those steps.

## Database bootstrap — future test session

**Do not run this yet.** First, the reviewed `runtime_enabled=true` apply must create RDS and the bootstrap task definition. The API-start and shutdown procedures must also be reviewed. Terraform registers this one-off task but never runs it automatically.

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

A task being `STOPPED` only means it finished; **exit code `0`** is what confirms success. If a command throws, stop there—do not continue or launch another task automatically.

## End a test session

First confirm that all staging data is disposable. The current RDS settings skip a final snapshot and delete automated backups. Assume that turning the runtime off permanently loses its database data.

Review the removal:

```powershell
terraform -chdir=infra\terraform\environments\staging plan -input=false -var="runtime_enabled=false"
```

With the current design, expect removal of the RDS instance, Valkey replication group, API and worker services and task definitions, database-bootstrap task definition, and the bootstrap and worker secret-read policies. Stop if Terraform also proposes deleting the network, ECR repositories, ECS cluster, or the two persistent application secrets.

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
