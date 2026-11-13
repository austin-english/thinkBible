terraform {
  # The state bucket was created by hand once (docs/aws-setup.md → Done).
  backend "s3" {
    bucket       = "thinkbible-tfstate-522779858032"
    key          = "envs/dev/terraform.tfstate"
    region       = "us-west-2"
    use_lockfile = true
    encrypt      = true
  }
}
