# Least privilege (research R19): the Lambdas may invoke only the configured Claude models, read
# the sources bucket, use the drafts bucket and the run ledger, and write their own logs.

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.prefix}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [for g in aws_cloudwatch_log_group.fn : "${g.arn}:*"]
  }

  statement {
    sid       = "ReadSources"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [var.sources_bucket_arn, "${var.sources_bucket_arn}/*"]
  }

  statement {
    sid       = "Drafts"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [module.drafts.arn, "${module.drafts.arn}/*"]
  }

  statement {
    sid       = "Ledger"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.runs.arn]
  }

  statement {
    sid     = "Bedrock"
    actions = concat(["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], var.extra_bedrock_actions)
    # Cross-region inference can run in any region, so foundation models use a region wildcard.
    resources = flatten([
      for m in var.bedrock_models : [
        "arn:aws:bedrock:*::foundation-model/${m}",
        "arn:aws:bedrock:*:${local.account_id}:inference-profile/us.${m}",
        "arn:aws:bedrock:*:${local.account_id}:inference-profile/global.${m}",
      ]
    ])
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "pipeline"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${local.prefix}-sfn"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "sfn" {
  statement {
    sid       = "InvokePipelineLambdas"
    actions   = ["lambda:InvokeFunction"]
    resources = flatten([for f in aws_lambda_function.fn : [f.arn, "${f.arn}:*"]])
  }

  # Step Functions delivers execution logs through CloudWatch Logs' log delivery API, which
  # doesn't support resource-level permissions.
  statement {
    sid = "LogDelivery"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "sfn" {
  name   = "pipeline"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn.json
}
