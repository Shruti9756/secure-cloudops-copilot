terraform {
  backend "s3" {
    bucket       = "secure-cloudops-copilot-tfstate-291667884598-us-east-1"
    key          = "states/development/platform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}