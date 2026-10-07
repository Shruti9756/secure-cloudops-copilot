data "aws_iam_policy_document" "document_queue_publish" {
  statement {
    sid       = "PublishDocumentProcessingMessages"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.document_processing.arn]
  }
}

resource "aws_iam_role_policy" "document_queue_publish" {
  name   = "secure-cloudops-${var.environment}-document-queue-publish"
  role   = module.ecs_roles.task_role_names["publisher"]
  policy = data.aws_iam_policy_document.document_queue_publish.json
}

data "aws_iam_policy_document" "document_queue_consume" {
  statement {
    sid    = "ConsumeDocumentProcessingMessages"
    effect = "Allow"

    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
    ]

    resources = [aws_sqs_queue.document_processing.arn]
  }
}

resource "aws_iam_role_policy" "document_queue_consume" {
  name   = "secure-cloudops-${var.environment}-document-queue-consume"
  role   = module.ecs_roles.task_role_names["worker"]
  policy = data.aws_iam_policy_document.document_queue_consume.json
}