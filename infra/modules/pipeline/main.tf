# The content pipeline in AWS (specs/001 research R7, R8, R19): a drafts bucket, the run ledger,
# five Lambdas sharing one bundle, and the Step Functions state machine that drives them.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  prefix     = "thinkbible-pipeline"
  account_id = data.aws_caller_identity.current.account_id
  handlers   = "thinkbible_pipeline.cloud.handlers"

  # Function name suffix → handler and timeout (seconds).
  functions = {
    start_run    = { handler = "${local.handlers}.start_run", timeout = 300 }
    plan_stage   = { handler = "${local.handlers}.plan_stage_handler", timeout = 300 }
    run_section  = { handler = "${local.handlers}.run_section", timeout = 900 }
    finish_stage = { handler = "${local.handlers}.finish_stage_handler", timeout = 120 }
    finish_run   = { handler = "${local.handlers}.finish_run", timeout = 300 }
  }
}

module "drafts" {
  source = "../storage"
  name   = "thinkbible-drafts-${local.account_id}"
  tags   = var.tags
}

resource "aws_dynamodb_table" "runs" {
  name         = "thinkbible-pipeline-runs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "runId"

  attribute {
    name = "runId"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "fn" {
  for_each          = local.functions
  name              = "/aws/lambda/${local.prefix}-${replace(each.key, "_", "-")}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_lambda_function" "fn" {
  for_each         = local.functions
  function_name    = "${local.prefix}-${replace(each.key, "_", "-")}"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = each.value.handler
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  timeout          = each.value.timeout
  memory_size      = 1024

  environment {
    variables = {
      DRAFTS_BUCKET        = module.drafts.id
      SOURCES_BUCKET       = var.sources_bucket_name
      LEDGER_TABLE         = aws_dynamodb_table.runs.name
      THINKBIBLE_REPO_ROOT = "/var/task"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.fn[each.key].name
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/vendedlogs/states/${local.prefix}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_sfn_state_machine" "pipeline" {
  name     = local.prefix
  type     = "STANDARD"
  role_arn = aws_iam_role.sfn.arn

  definition = templatefile("${path.module}/state_machine.asl.json.tftpl", {
    start_run_arn    = aws_lambda_function.fn["start_run"].arn
    plan_stage_arn   = aws_lambda_function.fn["plan_stage"].arn
    run_section_arn  = aws_lambda_function.fn["run_section"].arn
    finish_stage_arn = aws_lambda_function.fn["finish_stage"].arn
    finish_run_arn   = aws_lambda_function.fn["finish_run"].arn
    max_concurrency  = var.max_concurrency
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = false
    level                  = "ERROR"
  }

  tags = var.tags
}
