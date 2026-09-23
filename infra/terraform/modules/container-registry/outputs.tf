output "repository_urls" {
  description = "ECR URLs for the API and web images."
  value = {
    for name, repository in aws_ecr_repository.image :
    name => repository.repository_url
  }
}