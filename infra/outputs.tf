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
