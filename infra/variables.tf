# Define variables
variable "subscription_id" {
  type        = string
  description = "Azure subscription ID"
  validation {
    condition = var.subscription_id != null && var.subscription_id != ""
    error_message = "Subscription ID must be set"
  }
}

variable "resource_group_name" {
  type        = string
  description = "Name of the resource group"
  default     = "autothrottle-rg"
}

variable "resource_group_location" {
  type        = string
  description = "Location of the resource group"
  default     = "East US"
}

variable "virtual_network_name" {
  type        = string
  description = "Name of the virtual network"
  default     = "autothrottle-vnet"
}

variable "address_space" {
  type        = list(string)
  description = "Address space for the virtual network"
  default     = ["10.0.0.0/16"]
}

variable "subnet_name" {
  type        = string
  description = "Name of the subnet"
  default     = "autothrottle-subnet"
}

variable "subnet_address_prefixes" {
  type        = list(string)
  description = "Address prefixes for the subnet"
  default     = ["10.0.1.0/24"]
}

variable "network_security_group_name" {
  type        = string
  description = "Name of the network security group"
  default     = "autothrottle-nsg"
}

variable "vm_count" {
  type        = number
  description = "Number of virtual machines to create"
  default     = 5
}

variable "vm_size" {
  type        = string
  description = "Size of the virtual machine"
  default     = "Standard_D32as_v5"
}

variable "admin_username" {
  type        = string
  description = "Administrator username for the VMs"
  default     = "azureuser"
}

variable "admin_password" {
  type        = string
  description = "Administrator password for the VMs"
  default     = "P@ssw0rd123!"
  sensitive   = true
}

variable "public_ip_allocation_method" {
  type        = string
  description = "Allocation method for public IP"
  default     = "Dynamic"
}

variable "os_disk_size_gb" {
  type        = number
  description = "OS disk size in GB"
  default     = 256
}

variable "storage_account_type" {
  type        = string
  description = "Storage account type for the OS disk"
  default     = "Premium_LRS"
}

variable "image_publisher" {
  type        = string
  description = "Image publisher for VM"
  default     = "Canonical"
}

variable "image_offer" {
  type        = string
  description = "Image offer for VM"
  default     = "0001-com-ubuntu-server-focal"
}

variable "image_sku" {
  type        = string
  description = "Image SKU for VM"
  default     = "20_04-lts-gen2"
}

variable "image_version" {
  type        = string
  description = "Image version for VM"
  default     = "latest"
}

variable "tags" {
  type        = map(string)
  description = "Tags for resources"
  default = {
    Environment = "Dev"
    Project     = "AutoThrottle"
  }
}
