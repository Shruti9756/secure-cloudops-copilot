resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  tags = {
    Purpose = "github-actions-authentication"
  }

  lifecycle {
    prevent_destroy = true
  }
}

data "aws_iam_policy_document" "github_oidc_smoke_trust" {
  statement {
    sid     = "AllowOnlyThisRepositoryAndBranch"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:Shruti9756@103516233/secure-cloudops-copilot@1323171008:ref:refs/heads/codex/v04-aws-platform",
      ]
    }
  }
}

resource "aws_iam_role" "github_oidc_smoke" {
  name                 = "secure-cloudops-github-oidc-smoke"
  description          = "Identity-only GitHub OIDC test; no deployment permissions."
  assume_role_policy   = data.aws_iam_policy_document.github_oidc_smoke_trust.json
  max_session_duration = 3600

  tags = {
    Purpose = "github-oidc-identity-check"
  }
}