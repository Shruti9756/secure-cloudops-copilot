resource "aws_sqs_queue" "document_processing_dlq" {
  name                      = "secure-cloudops-${var.environment}-document-processing-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = {
    Name    = "secure-cloudops-${var.environment}-document-processing-dlq"
    Purpose = "document-processing-dead-letter"
  }
}

resource "aws_sqs_queue" "document_processing" {
  name                       = "secure-cloudops-${var.environment}-document-processing"
  message_retention_seconds  = 345600
  visibility_timeout_seconds = 300
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.document_processing_dlq.arn
    maxReceiveCount     = 5
  })

  tags = {
    Name    = "secure-cloudops-${var.environment}-document-processing"
    Purpose = "document-processing"
  }
}

resource "aws_sqs_queue_redrive_allow_policy" "document_processing" {
  queue_url = aws_sqs_queue.document_processing_dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.document_processing.arn]
  })
}