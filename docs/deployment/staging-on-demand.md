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