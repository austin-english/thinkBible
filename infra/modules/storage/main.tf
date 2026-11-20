# A private, versioned, encrypted, HTTPS-only S3 bucket. Used for the sources snapshot, the pipeline's drafts
# and the published packs (specs/001 research R2, R8, R14).

resource "aws_s3_bucket" "this" {
  bucket        = var.name
  force_destroy = false
  tags          = var.tags
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Every request must use TLS (AWS Security Hub S3.5). Other statements (the CDN's read access on
# the packs bucket) come in through var.policy_json: a bucket has only one policy.
data "aws_iam_policy_document" "this" {
  source_policy_documents = var.policy_json == null ? [] : [var.policy_json]

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket = aws_s3_bucket.this.id
  policy = data.aws_iam_policy_document.this.json
  # Public access is blocked first, so the policy can never be applied to an open bucket.
  depends_on = [aws_s3_bucket_public_access_block.this]
}
