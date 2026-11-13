# Copy these into pipeline/config/aws.toml after `terraform apply`.

output "drafts_bucket" {
  description = "drafts_bucket"
  value       = module.drafts.id
}

output "ledger_table" {
  description = "ledger_table"
  value       = aws_dynamodb_table.runs.name
}

output "state_machine_arn" {
  description = "state_machine_arn"
  value       = aws_sfn_state_machine.pipeline.arn
}
