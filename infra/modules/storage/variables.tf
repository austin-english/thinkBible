variable "name" {
  description = "Bucket name: thinkbible-<purpose>-<account id> (docs/aws-setup.md)."
  type        = string
}

variable "tags" {
  description = "Tags for the bucket."
  type        = map(string)
  default     = {}
}

variable "policy_json" {
  description = "Extra bucket policy statements (JSON), merged with the module's HTTPS-only rule. The packs bucket passes the CDN's read access here."
  type        = string
  default     = null
}
