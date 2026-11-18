# Copy into pipeline/config/aws.toml.

output "sources_bucket" {
  value = module.sources.id
}

output "drafts_bucket" {
  value = module.pipeline.drafts_bucket
}

output "ledger_table" {
  value = module.pipeline.ledger_table
}

output "state_machine_arn" {
  value = module.pipeline.state_machine_arn
}

output "packs_bucket" {
  value = module.packs.id
}

output "distribution_id" {
  value = module.cdn.distribution_id
}

output "cdn_base_url" {
  value = "https://${module.cdn.domain_name}"
}
