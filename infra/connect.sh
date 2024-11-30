#!/bin/bash

# Prompt for root password
read -p "Enter root password: " ROOT_PASSWORD
echo

if [ -z "$ROOT_PASSWORD" ]; then
    echo "❌ Root password cannot be empty"
    exit 1
fi


# Login to Azure if not already logged in
echo "🔄 Checking Azure login status..."
az account show > /dev/null 2>&1 || az login

# Get resource group name
RG="autothrottle-rg"
echo "📁 Using resource group: $RG"

# Set proper permissions and create directories
echo "🔒 Setting proper SSH directory permissions..."
mkdir -p ~/.ssh/config
chmod 700 ~/.ssh
chmod 700 ~/.ssh/config

# Create single SSH key if it doesn't exist
KEY_FILE="$HOME/.ssh/autothrottle"
if [ ! -f "$KEY_FILE" ]; then
    echo "🔑 Creating SSH key pair..."
    mkdir -p "$(dirname "$KEY_FILE")"
    ssh-keygen -t rsa -b 4096 -f "$KEY_FILE" -N ""
fi

# Set proper permissions
chmod 600 "$KEY_FILE"
chmod 644 "${KEY_FILE}.pub"

# Create base SSH config
echo "📝 Creating SSH config file..."
cat > ~/.ssh/config << EOL
Host autothrottle-*
    IdentityFile ${KEY_FILE}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    PubkeyAuthentication yes
    PasswordAuthentication yes
    User root
EOL

# Get VM information
echo "🔍 Fetching VM information..."

# Get VM names and IPs into arrays
VM_NAMES=($(az vm list-ip-addresses -g $RG --query "[].virtualMachine.name" -o tsv))
VM_IPS=($(az vm list-ip-addresses -g $RG --query "[].virtualMachine.network.publicIpAddresses[0].ipAddress" -o tsv))

echo "📋 Found ${#VM_NAMES[@]} VMs:"
for i in "${!VM_NAMES[@]}"; do
    echo "${VM_NAMES[$i]} - ${VM_IPS[$i]}"
done


# Process each VM
for i in "${!VM_NAMES[@]}"; do
    name="${VM_NAMES[$i]}"
    ip="${VM_IPS[$i]}"
    
    echo "
📌 Processing VM: $name ($ip)
------------------------------------------------"
    
    # Add to SSH config
    echo "➕ Adding to SSH config..."
    cat >> ~/.ssh/config << EOL

Host $name
    HostName $ip
EOL
    
    # Copy SSH key to admin user
    echo "🔑 Copying SSH key to admin user..."
    ssh-copy-id -f -i "$KEY_FILE" "auto@$ip"
    
    # Verify admin user SSH access
    ssh -i "$KEY_FILE" -o BatchMode=yes "auto@$ip" exit 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Admin SSH key setup successful"
    else
        # Setup root access with proper waiting
        echo "👑 Setting up root access..."
        ssh -i "$KEY_FILE" "auto@$ip" "
            # Set root password and SSH config in one sudo session
            sudo sh -c '
                echo \"root:$ROOT_PASSWORD\" | chpasswd
                sed -i \"s/#PermitRootLogin prohibit-password/PermitRootLogin yes/\" /etc/ssh/sshd_config
                sed -i \"s/PermitRootLogin prohibit-password/PermitRootLogin yes/\" /etc/ssh/sshd_config
                systemctl restart sshd
            '
        "
    fi
    
    # Add the public key directly to root's authorized_keys
    echo "🔑 Setting up root SSH key..."
    PUB_KEY=$(cat "${KEY_FILE}.pub")
    ssh -i "$KEY_FILE" "auto@$ip" "
        sudo sh -c '
            mkdir -p /root/.ssh
            echo \"$PUB_KEY\" > /root/.ssh/authorized_keys
            chmod 700 /root/.ssh
            chmod 600 /root/.ssh/authorized_keys
            chown -R root:root /root/.ssh
        '
    "
    
    # Verify root SSH access
    echo "🔍 Verifying root access..."
    if ssh -i "$KEY_FILE" -o BatchMode=yes "root@$ip" exit 2>/dev/null; then
        echo "✅ Root SSH key setup successful"
    else
        echo "❌ Root SSH key setup failed for $name"
    fi
    
    echo "✅ Setup complete for $name"
    echo "------------------------------------------------"
done

# Test connections
echo "🧪 Testing SSH connections..."
for name in "${VM_NAMES[@]}"; do
    printf "Testing %-15s: " "$name"
    if ssh -o BatchMode=yes "$name" whoami 2>/dev/null | grep -q "root"; then
        echo "✅ Success"
    else
        echo "❌ Failed"
    fi
done

echo "
🎉 SSH setup process completed!
👉 You should now be able to use:
    ssh root@autothrottle-1 whoami 
    ssh root@autothrottle-2 whoami
    ssh root@autothrottle-3 whoami
    to test SSH access to the VMs.
"