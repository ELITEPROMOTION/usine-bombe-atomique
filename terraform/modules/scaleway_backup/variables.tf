variable "bucket_name" {
  type        = string
  description = "Globally unique bucket name"
}

variable "region" {
  type    = string
  default = "fr-par"
}

variable "retention_days" {
  type        = number
  description = "Reference retention (used by lifecycle_expiration_days unless overridden)"
  default     = 90
}

variable "enable_versioning" {
  type    = bool
  default = true
}

variable "lifecycle_glacier_transition_days" {
  type    = number
  default = 30
}

variable "lifecycle_expiration_days" {
  type    = number
  default = 365
}

variable "acl" {
  type    = string
  default = "private"
}

variable "enforce_tls" {
  type    = bool
  default = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
