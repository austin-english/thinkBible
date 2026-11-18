# CloudFront in front of the packs bucket (specs/001 R14, contracts/cdn-layout.md): the only way to
# read published packs. The bucket stays private; origin access control signs CloudFront's
# requests, and the bucket policy allows only this distribution.

data "aws_cloudfront_cache_policy" "optimized" {
  # Honors each object's Cache-Control (5 minutes for index.json and draft files, a year for
  # live files) and compresses with gzip and brotli.
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_origin_access_control" "packs" {
  name                              = var.bucket_id
  description                       = "CloudFront reads the ThinkBible packs bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "packs" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "ThinkBible content packs (draft/ and live/)"
  price_class     = "PriceClass_100"
  tags            = var.tags

  origin {
    origin_id                = "packs"
    domain_name              = var.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.packs.id
  }

  default_cache_behavior {
    target_origin_id       = "packs"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

data "aws_iam_policy_document" "packs" {
  statement {
    sid       = "CloudFrontReadsPacks"
    actions   = ["s3:GetObject"]
    resources = ["${var.bucket_arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.packs.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "packs" {
  bucket = var.bucket_id
  policy = data.aws_iam_policy_document.packs.json
}
