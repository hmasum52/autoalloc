### Prerequisites
1. Azure Subscription
1. Install [Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli)
1. Install [OpenTofu](https://opentofu.org/docs/main/intro/install/)

### Create tfvars file
1. Create a `terraform.tfvars` file in the `infra` directory
    ```bash
    cp terraform.tfvars.example terraform.tfvars
    ```
    replace `subscription_id` with your Azure Subscription ID.

    You may need to add `tenant_id`, `client_id` etc. depending on your Azure setup. Please refer to the [Azure Provider: Authenticating using the Azure CLI](https://search.opentofu.org/provider/hashicorp/azurerm/latest/docs/guides/azure_cli) documentation for more information.

### Build Infrastructure
1. Initialize Terraform
    ```bash
    tofu init
    ```
2. Validate the infrastructure
    ```bash
    tofu validate
    ```
2. Plan the infrastructure
    ```bash
    tofu plan
    ```
3. Apply the infrastructure
    ```bash
    tofu apply --auto-approve
    ```
4. Refresh the infrastructure
    ```bash
    tofu refresh
    ```
5. Destroy the infrastructure
    ```bash
    tofu destroy --auto-approve
    ```


Reference: https://developer.hashicorp.com/terraform/tutorials/azure-get-started/azure-build