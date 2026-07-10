# infra/main.tf
# Provisions the Azure foundation for the analytics platform into the EXISTING
# resource group (ecom-analytics-rg). Creates:
#   - Azure Container Registry (ACR)  â€” stores the frontend/backend images
#   - Key Vault                       â€” stores secrets (Databricks creds, JWT secret)
#   - Log Analytics workspace         â€” required backing store for Container Apps logs
#   - Container Apps Environment       â€” the runtime that hosts the two container apps
#
# The container apps themselves are added in Step 6.4, once images are pushed.

terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  resource_provider_registrations = "none"
}

# Reference the resource group IT already created (do not create it).
data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

# Current identity (you) â€” used to grant yourself Key Vault secret access.
data "azurerm_client_config" "current" {}

# ---------- Container Registry ----------
resource "azurerm_container_registry" "acr" {
  name                = var.acr_name
  resource_group_name = data.azurerm_resource_group.main.name
  location            = data.azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true # simplest path for Container Apps to pull; revisit with managed identity later

  tags = var.tags
}

# ---------- Log Analytics (backing store for Container Apps) ----------
resource "azurerm_log_analytics_workspace" "logs" {
  name                = "${var.prefix}-logs"
  resource_group_name = data.azurerm_resource_group.main.name
  location            = data.azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = var.tags
}

# ---------- Container Apps Environment ----------
resource "azurerm_container_app_environment" "env" {
  name                       = "${var.prefix}-env"
  resource_group_name        = data.azurerm_resource_group.main.name
  location                   = data.azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.logs.id

  tags = var.tags
}

# ---------- Key Vault ----------
resource "azurerm_key_vault" "kv" {
  name                       = var.key_vault_name
  resource_group_name        = data.azurerm_resource_group.main.name
  location                   = data.azurerm_resource_group.main.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  enable_rbac_authorization  = true # use Azure RBAC for secret access (modern approach)

  tags = var.tags
}

# Grant yourself "Key Vault Secrets Officer" so you can add/read secrets.
resource "azurerm_role_assignment" "kv_admin" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}
# ---------- Storage Account (operational store for app users / RBAC) ----------
# Backs admin-managed login + RBAC via a Table Storage `users` table.
# Operational store, separate from the Databricks lakehouse (clean OLTP / OLAP split).
resource "azurerm_storage_account" "auth" {
  name                     = var.auth_storage_account_name
  resource_group_name      = data.azurerm_resource_group.main.name
  location                 = data.azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"

  tags = var.tags
}

resource "azurerm_storage_table" "users" {
  name                 = "users"
  storage_account_name = azurerm_storage_account.auth.name
}

# Connection string into Key Vault (consistent with the Databricks creds).
resource "azurerm_key_vault_secret" "tables_conn" {
  name         = "tables-connection-string"
  value        = azurerm_storage_account.auth.primary_connection_string
  key_vault_id = azurerm_key_vault.kv.id

  depends_on = [azurerm_role_assignment.kv_admin]
}