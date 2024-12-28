#!/bin/bash
set -ex

# https://kubernetes.io/docs/setup/production-environment/container-runtimes/
#  Installing Container Runtimes...

# Disabling swap (required for Kubernetes)
swapoff -a
sed -i '/swap/d' /etc/fstab

# Load necessary kernel modules
cat <<EOF | tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

modprobe overlay
modprobe br_netfilter

# Set required sysctl parameters
cat <<EOF | tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF

echo Apply sysctl params without reboot
sysctl --system

echo Verify that net.ipv4.ip_forward is set to 1 with:
sysctl net.ipv4.ip_forward

# Install containerd (newer version)
# https://docs.docker.com/engine/install/ubuntu/#install-using-the-repository
echo "Add Docker's official GPG key:" 
apt-get update -y
apt-get install ca-certificates curl -y
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo "Add the repository to Apt sources:"
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y

echo  "Install containerd (newer version):"
apt-get install -y containerd.io

echo Configure containerd to use systemd cgroup driver
mkdir -p /etc/containerd
containerd config default | tee /etc/containerd/config.toml
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml

echo Restart containerd to apply changes
systemctl restart containerd

echo "Installing kubeadm"
# https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/
apt-get update
# apt-transport-https may be a dummy package; if so, you can skip that package
apt-get install -y apt-transport-https ca-certificates curl gpg

# Add Kubernetes repository (updated for newer versions)
# If the directory `/etc/apt/keyrings` does not exist, it should be created before the curl command, read the note below.
# sudo mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.32/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
# This overwrites any existing configuration in /etc/apt/sources.list.d/kubernetes.list
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.32/deb/ /' | tee /etc/apt/sources.list.d/kubernetes.list

# Install Kubernetes components (latest 1.32.x versions)
apt-get update
apt-get install -y kubelet kubeadm kubectl
# pin the versions to prevent accidental upgrades
apt-mark hold kubelet kubeadm kubectl


# Load necessary kernel modules
cat <<EOF | tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

modprobe overlay
modprobe br_netfilter

sysctl --system

echo "Setting up Kubernetes cluster..."
# https://kubernetes.io/docs/reference/setup-tools/kubeadm/
#  https://kubernetes.io/docs/concepts/cluster-administration/addons/#networking-and-network-policy

if [ "$1" = master ]; then
    echo "Initializing Kubernetes cluster with newer networking configs"
    # https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/
    PUBLIC_IP=$(curl ifconfig.me && echo "")
    echo "Public IP: $PUBLIC_IP"
    kubeadm init \
        --pod-network-cidr=10.244.0.0/16 \
        --apiserver-advertise-address=$(hostname -i) \
        --apiserver-cert-extra-sans=$PUBLIC_IP \
        --control-plane-endpoint=$PUBLIC_IP \
        --kubernetes-version=v1.32.0 \
        --node-name=master

    echo "Setting up Kubernetes credentials..."
    mkdir -p $HOME/.kube
    cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
    chown $(id -u):$(id -g) $HOME/.kube/config

    echo "Installing Flannel net    working..."
    kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml

    echo "Creating join command for workers..."
    kubeadm token create --print-join-command > join-command
    cp $HOME/.kube/config kube-config

    echo "Setting up Locust..."
    echo "Installing Locust dependencies..."
    apt-get install -y python3-venv
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt

    echo "Making Locust available globally..."
    ln -sf /root/venv/bin/locust /usr/local/bin/locust

elif [ "$1" = worker ]; then
    echo "Joining Kubernetes cluster..."
    bash join-command

    # Setup Kubernetes credentials
    mkdir -p $HOME/.kube
    cp kube-config $HOME/.kube/config
    chown $(id -u):$(id -g) $HOME/.kube/config

    echo "Running worker daemon in background with improved session handling..."
    tmux new-session -d -s worker-daemon './worker-daemon.py'
    tmux set-option -t worker-daemon remain-on-exit on
fi