output "github_oidc_provider_arn" {
  description = "Account-wide GitHub OIDC provider."
  value       = aws_iam_openid_connect_provider.github.arn
}

output "github_oidc_smoke_role_arn" {
  description = "Role reserved for a manual identity-only workflow test."
  value       = aws_iam_role.github_oidc_smoke.arn
}