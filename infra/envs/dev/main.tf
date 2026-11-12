# Dev environment, us-west-2 (docs/aws-setup.md → Regions).
#
#   make lambda-bundle
#   cd infra/envs/dev && terraform init && terraform apply
#
# Then copy `terraform output` into pipeline/config/envs/dev.toml.

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
}

# The frozen source snapshot (specs/001 US4). One bucket per account, shared by every env.
module "sources" {
  source = "../../modules/storage"
  name   = "thinkbible-sources-${local.account_id}"
}

module "pipeline" {
  source              = "../../modules/pipeline"
  env                 = "dev"
  sources_bucket_name = module.sources.id
  sources_bucket_arn  = module.sources.arn
  lambda_zip_path     = "${path.root}/../../../pipeline/out/lambda.zip"

  # Keep in step with pipeline/config/settings.toml (checked by tests/unit/test_infra_sync.py).
  max_concurrency = 10
  bedrock_models = [
    "anthropic.claude-haiku-5-5",
    "anthropic.claude-sonnet-5-5",
    "anthropic.claude-opus-5-5",
  ]
}
