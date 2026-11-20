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

# The published packs (specs/001 US3): prefixes draft/ and live/, readable only through the CDN.
module "packs" {
  source = "./modules/storage"
  name   = "thinkbible-packs-${local.account_id}"
  # CloudFront's read access, merged with the HTTPS-only rule into the bucket's one policy.
  policy_json = module.cdn.packs_policy_json
}

# The packs bucket policy moved from the cdn module to the storage module (2026-11-19, T086).
moved {
  from = module.cdn.aws_s3_bucket_policy.packs
  to   = module.packs.aws_s3_bucket_policy.this
}

module "cdn" {
  source                      = "./modules/cdn"
  bucket_id                   = module.packs.id
  bucket_arn                  = module.packs.arn
  bucket_regional_domain_name = module.packs.bucket_regional_domain_name
}

module "pipeline" {
  source              = "./modules/pipeline"
  sources_bucket_name = module.sources.id
  sources_bucket_arn  = module.sources.arn
  lambda_zip_path     = "${path.root}/../pipeline/out/lambda.zip"

  # A run that passes its gate publishes the book to the draft channel (R14).
  packs_bucket_name = module.packs.id
  packs_bucket_arn  = module.packs.arn
  distribution_id   = module.cdn.distribution_id
  distribution_arn  = module.cdn.distribution_arn

  # Keep in step with pipeline/config/settings.toml (checked by tests/unit/test_infra_sync.py).
  # 3 sections at a time: the Claude API account's per-minute limits are still low.
  max_concurrency = 3
  # The Claude API key (an SSM SecureString created by hand, never in Terraform state).
  anthropic_api_key_parameter = "anthropic-api-key"
  # The `bedrock` profile's models (Claude 4.x until Bedrock opens 5.5 for this account).
  bedrock_models = [
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-sonnet-4-6",
    "us.anthropic.claude-opus-4-6-v1",
  ]
}

