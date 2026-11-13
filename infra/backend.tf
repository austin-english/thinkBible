terraform {
  # The state bucket was created by hand once (docs/aws-setup.md → Done).
  # One environment (2026-11-13): this is the only Terraform root. The state moved here from
  # envs/dev/terraform.tfstate with `terraform init -migrate-state`.
  backend "s3" {
    bucket       = "thinkbible-tfstate-522779858032"
    key          = "thinkbible/terraform.tfstate"
    region       = "us-west-2"
    use_lockfile = true
    encrypt      = true
  }
}
