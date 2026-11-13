variable "name" {
  description = "Bucket name: thinkbible-<purpose>-<account id> (docs/aws-setup.md)."
  type        = string
}

variable "tags" {
  description = "Tags for the bucket."
  type        = map(string)
  default     = {}
}
