variable "bucket_id" {
  description = "The packs bucket's name."
  type        = string
}

variable "bucket_arn" {
  description = "The packs bucket's ARN."
  type        = string
}

variable "bucket_regional_domain_name" {
  description = "The packs bucket's regional domain name (the CloudFront origin)."
  type        = string
}

variable "tags" {
  description = "Tags for the distribution."
  type        = map(string)
  default     = {}
}
