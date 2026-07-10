# infra/variables.tf

variable "subscription_id" {
  description = "Azure subscription ID (from `az account show`)"
  type        = string
  default     = "00000000-0000-0000-0000-000000000000"
}

variable "resource_group_name" {
  description = "Existing resource group created by IT"
  type        = string
  default     = "ecom-analytics-rg"
}

variable "prefix" {
  description = "Short prefix for resource names"
  type        = string
  default     = "analytics-platform"
}

# ACR and Key Vault names must be GLOBALLY unique. ACR: alphanumeric only, 5-50
# chars. Key Vault: alphanumeric + hyphens, 3-24 chars. Adjust if taken.
variable "acr_name" {
  description = "Container Registry name (globally unique, alphanumeric only)"
  type        = string
  default     = "analyticsplatformacr"
}

variable "key_vault_name" {
  description = "Key Vault name (globally unique, 3-24 chars)"
  type        = string
  default     = "analytics-kv"
}

variable "tags" {
  description = "Tags applied to all resources (cost tracking / FinOps)"
  type        = map(string)
  default = {
    project     = "analytics-platform"
    environment = "production"
    owner       = "sia"
    cost-center = "ecom-analytics"
  }
}
variable "auth_storage_account_name" {
  description = "Storage account for the app users table (globally unique, 3-24 lowercase alphanumeric)"
  type        = string
  default     = "appauthstore"
}