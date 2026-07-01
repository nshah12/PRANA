variable "environment" {
  type        = string
  description = "dev | staging | prod"
}

variable "services" {
  type        = list(string)
  default     = ["prana-api", "prana-ai", "prana-ask"]
  description = "ECR repository names to create"
}

variable "image_retention_count" {
  type        = number
  default     = 10
  description = "Number of tagged images to keep per repo"
}

variable "allowed_account_ids" {
  type        = list(string)
  default     = []
  description = "Additional AWS account IDs allowed to pull images (e.g. staging account pulling prod ECR)"
}

variable "tags" {
  type    = map(string)
  default = {}
}
