# infra/outputs.tf
# Values needed in Step 6.4 (pushing images, deploying container apps).

output "acr_login_server" {
  description = "ACR login server (e.g. demoplatformacr.azurecr.io)"
  value       = azurerm_container_registry.acr.login_server
}

output "acr_name" {
  value = azurerm_container_registry.acr.name
}

output "key_vault_name" {
  value = azurerm_key_vault.kv.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.kv.vault_uri
}

output "container_app_environment_id" {
  value = azurerm_container_app_environment.env.id
}

output "container_app_environment_name" {
  value = azurerm_container_app_environment.env.name
}
output "auth_storage_account_name" {
  value = azurerm_storage_account.auth.name
}

output "auth_storage_connection_string" {
  value     = azurerm_storage_account.auth.primary_connection_string
  sensitive = true
}