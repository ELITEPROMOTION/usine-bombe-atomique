terraform {
  required_providers {
    scaleway = { source = "scaleway/scaleway" }
  }
}

resource "scaleway_object_bucket" "this" {
  name   = var.bucket_name
  region = var.region
  tags   = var.tags

  versioning {
    enabled = var.enable_versioning
  }

  lifecycle_rule {
    id      = "transition-to-glacier"
    enabled = true

    transition {
      days          = var.lifecycle_glacier_transition_days
      storage_class = "GLACIER"
    }

    expiration {
      days = var.lifecycle_expiration_days
    }
  }
}

resource "scaleway_object_bucket_acl" "this" {
  bucket = scaleway_object_bucket.this.id
  acl    = var.acl
}

resource "scaleway_object_bucket_policy" "deny_unencrypted" {
  count  = var.enforce_tls ? 1 : 0
  bucket = scaleway_object_bucket.this.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          scaleway_object_bucket.this.id,
          "${scaleway_object_bucket.this.id}/*",
        ]
        Condition = {
          Bool = { "aws:SecureTransport" = "false" }
        }
      },
    ]
  })
}
