#!/bin/bash
set -ex

# Prompt for master node public IP
read -p "Enter master node public IP: " PUBLIC_IP
echo "🔗 Using master node public IP: $PUBLIC_IP"

# check SSH connections for the 3 VMs
for i in {1..3}; do
    if [ "$(ssh root@autothrottle-$i whoami)" != root ]; then
        echo "SSH connection to autothrottle-$i failed"
        echo "Please make sure the command 'ssh root@autothrottle-$i whoami' works"
        exit 1
    fi
done

# upload to master (autothrottle-1)
rsync -avz evaluation.py hotel-reservation requirements.txt setup-node.sh utils.py worker-daemon.py root@autothrottle-1:

# setup master
if ssh root@autothrottle-1 kubectl get nodes &> /dev/null; then
    ssh root@autothrottle-1 kubectl get nodes
    echo "Control-plane node is already running, skipping setup."
else
    echo "Control-plane node is not running, setting up..."
    ssh root@autothrottle-1 ./setup-node.sh master $PUBLIC_IP
fi

# download from master
mkdir -p tmp
rsync -avz root@autothrottle-1:"{join-command,kube-config}" tmp/

# setup workers (autothrottle-2 and autothrottle-3)
for i in {2..3}; do
    # upload to worker
    rsync -avz setup-node.sh worker-daemon.py tmp/join-command tmp/kube-config root@autothrottle-$i:
    
    # setup worker
    ssh root@autothrottle-$i ./setup-node.sh worker
done

# cleanup
rm tmp/join-command tmp/kube-config
rmdir tmp