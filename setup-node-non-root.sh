#!/bin/bash
set -ex

# Disabling swap (required for Kubernetes)
sudo swapoff -a
sudo sed -i '/swap/d' /etc/fstab

# Load necessary kernel modules
cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
sudo modprobe overlay
sudo modprobe br_netfilter

# Set required sysctl parameters
cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
echo "Apply sysctl params without reboot"
sudo sysctl --system
echo "Verify that net.ipv4.ip_forward is set to 1 with:"
sysctl net.ipv4.ip_forward

# Install containerd (newer version)
echo "Add Docker's official GPG key:" 
sudo apt-get update -y
sudo apt-get install ca-certificates curl -y
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "Add the repository to Apt sources:"
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -y

echo "Install containerd (newer version):"
sudo apt-get install -y containerd.io

echo "Configure containerd to use systemd cgroup driver"
sudo mkdir -p /etc/containerd
containerd config default | sudo tee /etc/containerd/config.toml
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml

echo "Restart containerd to apply changes"
sudo systemctl restart containerd

echo "Installing kubeadm"
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl gpg

# Add Kubernetes repository (updated for newer versions)
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.32/deb/Release.key | gpg --dearmor | sudo tee /etc/apt/keyrings/kubernetes-apt-keyring.gpg > /dev/null

# This overwrites any existing configuration in /etc/apt/sources.list.d/kubernetes.list
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.32/deb/ /' | sudo tee /etc/apt/sources.list.d/kubernetes.list

# Install Kubernetes components (latest 1.32.x versions)
sudo apt-get update
sudo apt-get install -y kubelet kubeadm kubectl

# Pin the versions to prevent accidental upgrades
sudo apt-mark hold kubelet kubeadm kubectl

# Load necessary kernel modules
cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
sudo modprobe overlay
sudo modprobe br_netfilter
sudo sysctl --system

echo "Setting up Kubernetes cluster..."
if [ "$1" = master ]; then
    echo "Initializing Kubernetes cluster with newer networking configs"
    PUBLIC_IP=$(curl ifconfig.me && echo "")
    echo "Public IP: $PUBLIC_IP"
    sudo kubeadm init \
        --pod-network-cidr=10.244.0.0/16 \
        --apiserver-advertise-address=$(hostname -i | awk '{print $1}') \
        --kubernetes-version=v1.32.0 \
        --node-name=master

    echo "Setting up Kubernetes credentials..."
    mkdir -p $HOME/.kube
    sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
    sudo chown $(id -u):$(id -g) $HOME/.kube/config

    echo "Installing Flannel networking..."
    kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml

    echo "Creating join command for workers..."
    sudo kubeadm token create --print-join-command > join-command
    sudo cp $HOME/.kube/config kube-config

    echo "Setting up Locust..."
    echo "Installing Locust dependencies..."
    sudo apt-get install -y python3-venv
    cd autoalloc
    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt

    echo "Making Locust available globally..."
    sudo ln -sf /root/venv/bin/locust /usr/local/bin/locust
elif [ "$1" = worker ]; then
    echo "Joining Kubernetes cluster..."
    sudo bash join-command --node-name=$2

    # Setup Kubernetes credentials
    mkdir -p $HOME/.kube
    sudo cp kube-config $HOME/.kube/config
    sudo chown $(id -u):$(id -g) $HOME/.kube/config

    echo "Running worker daemon in background with improved session handling..."
    cd autoalloc
    tmux new-session -d -s worker-daemon './worker-daemon.py'
    tmux set-option -t worker-daemon remain-on-exit on
fi