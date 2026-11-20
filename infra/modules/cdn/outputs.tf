output "distribution_id" {
  description = "For CloudFront invalidations (aws.toml distribution_id)."
  value       = aws_cloudfront_distribution.packs.id
}

output "distribution_arn" {
  description = "For the pipeline's invalidation permission."
  value       = aws_cloudfront_distribution.packs.arn
}

output "domain_name" {
  description = "The CDN's domain, e.g. d1234.cloudfront.net."
  value       = aws_cloudfront_distribution.packs.domain_name
}

output "packs_policy_json" {
  description = "The packs bucket's policy statement for this distribution; applied by the storage module."
  value       = data.aws_iam_policy_document.packs.json
}
