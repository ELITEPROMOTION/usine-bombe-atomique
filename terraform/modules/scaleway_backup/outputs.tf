output "bucket_name" {
  value = scaleway_object_bucket.this.name
}

output "bucket_id" {
  value = scaleway_object_bucket.this.id
}

output "endpoint" {
  value = scaleway_object_bucket.this.endpoint
}

output "region" {
  value = scaleway_object_bucket.this.region
}
