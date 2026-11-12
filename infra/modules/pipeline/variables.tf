variable "env" {
  description = "Environment name: dev or prod."
  type        = string
}

variable "sources_bucket_name" {
  description = "The sources snapshot bucket (read-only to the pipeline)."
  type        = string
}

variable "sources_bucket_arn" {
  description = "ARN of the sources snapshot bucket."
  type        = string
}

variable "lambda_zip_path" {
  description = "Path to pipeline/out/lambda.zip (make lambda-bundle)."
  type        = string
}

variable "max_concurrency" {
  description = "Sections run in parallel per stage. Keep equal to concurrency in pipeline/config/settings.toml."
  type        = number
  default     = 10
}

variable "bedrock_models" {
  description = "Bedrock model or inference-profile IDs the pipeline may invoke, exactly as in pipeline/config/settings.toml."
  type        = list(string)
}

variable "extra_bedrock_actions" {
  description = "Extra IAM actions, e.g. bedrock-mantle:CreateInference if settings.toml switches to the Mantle endpoint (research R19)."
  type        = list(string)
  default     = []
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the Lambdas and the state machine."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags for every resource."
  type        = map(string)
  default     = {}
}
