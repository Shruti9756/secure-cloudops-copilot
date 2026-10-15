data "aws_iam_policy_document" "github_api_image_publisher_trust" {
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

resource "aws_iam_role" "github_api_image_publisher" {
  name                 = "secure-cloudops-github-api-image-publisher"
  description          = "GitHub OIDC publisher for the staging API ECR repository only."
  assume_role_policy   = data.aws_iam_policy_document.github_api_image_publisher_trust.json
  max_session_duration = 3600

  tags = {
    Purpose = "github-api-image-publication"
  }
}

data "aws_iam_policy_document" "github_api_image_publish" {
  statement {
    sid       = "AuthenticateToEcrInApprovedRegion"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = ["us-east-1"]
    }
  }

  statement {
    sid    = "PublishAndVerifyOnlyStagingApiImages"
    effect = "Allow"

    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]

    resources = [
      "arn:aws:ecr:us-east-1:291667884598:repository/secure-cloudops-staging/api",
    ]
  }
}

resource "aws_iam_role_policy" "github_api_image_publish" {
  name   = "publish-only-secure-cloudops-staging-api"
  role   = aws_iam_role.github_api_image_publisher.name
  policy = data.aws_iam_policy_document.github_api_image_publish.json
}

output "github_api_image_publisher_role_arn" {
  description = "GitHub OIDC role limited to publishing staging API images."
  value       = aws_iam_role.github_api_image_publisher.arn
}