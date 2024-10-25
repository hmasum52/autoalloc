### Prerequisites
1. Azure Subscription
1. Install [Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli)
1. Install [OpenTofu](https://opentofu.org/docs/main/intro/install/)

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
    tofu apply
    ```


Reference: https://developer.hashicorp.com/terraform/tutorials/azure-get-started/azure-build