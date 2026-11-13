# ThinkBible in AWS, us-west-2 (docs/aws-setup.md → Regions). One environment: draft and live
# content are two channels of the packs bucket, not two copies of the infrastructure (2026-11-13).
#
#   make lambda-bundle
#   cd infra && terraform init && terraform apply
#
# Then copy `terraform output` into pipeline/config/aws.toml.

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
}

# The frozen source snapshot (specs/001 US4).
module "sources" {
  source = "./modules/storage"
  name   = "thinkbible-sources-${local.account_id}"
}

module "pipeline" {
  source              = "./modules/pipeline"
  sources_bucket_name = module.sources.id
  sources_bucket_arn  = module.sources.arn
  lambda_zip_path     = "${path.root}/../pipeline/out/lambda.zip"

  # Keep in step with pipeline/config/settings.toml (checked by tests/unit/test_infra_sync.py).
  max_concurrency = 10
  # Claude 4.x until the 5.5 models open up for this account (settings.toml has the details).
  bedrock_models = [
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-sonnet-4-6",
    "us.anthropic.claude-opus-4-6-v1",
  ]
}

# US3 adds the packs bucket (prefixes draft/ and live/) and one CloudFront distribution.
