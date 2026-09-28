# Staging on-demand runtime

This procedure is for the **staging** Terraform environment and **synthetic data only**. It is not a pause button: turning the runtime off deletes the staging PostgreSQL database and Valkey cache.

The persistent network, ECR repositories, ECS cluster, and two application secrets remain when the runtime is off. Therefore, off does not mean zero AWS cost.

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

For the current code and state, expect **11 adds, 0 changes, 0 destroys**. The additions include two Secrets Manager secrets, which can have ongoing cost. Read the resource names, not just the count.

Only after deciding to create those resources, run:

```powershell
terraform -chdir=infra\terraform\environments\staging apply -var="runtime_enabled=false"
```

Terraform will show a **fresh plan** and ask for approval. Check it again before typing `yes`. If it differs from what you expected, type `no` and stop.

## Start a planned test session
**Hold for now:** Do not run this section until the separate database-bootstrap, API-start, and session-shutdown steps are documented and reviewed. Turning the runtime on creates RDS and Valkey while the API remains stopped.

First review:

```powershell
terraform -chdir=infra\terraform\environments\staging plan -input=false -var="runtime_enabled=true"
```

After the supporting setup is applied, the current design should add six runtime resources, including the RDS instance and Valkey replication group, with no destroys. RDS and Valkey can incur charges while they exist.

Only when ready for a cloud test, run:

```powershell
terraform -chdir=infra\terraform\environments\staging apply -var="runtime_enabled=true"
```

Review the fresh plan before typing `yes`. Record when the database and cache are created.

**This does not start the application.** The API service has `desired_count = 0`. Running the one-off database bootstrap task and then starting the API require separate reviewed instructions; do not improvise those steps.

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

With the current design, expect removal of the RDS instance, Valkey replication group, API service, API task definition, database-bootstrap task definition, and bootstrap secret-read policy. Stop if Terraform also proposes deleting the network, ECR repositories, ECS cluster, or the two persistent application secrets.

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