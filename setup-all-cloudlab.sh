#!/bin/bash
set -ex

usrname="ubuntu"
pem_file="dr_adnan_keypair.pem"
declare -a ips=(
    [0]=ubuntu@10.10.0.158
    [1]=ubuntu@10.10.2.172
    [2]=ubuntu@10.10.1.219
)

# check SSH connections and create autoalloc directory
for i in {0..2}; do
    if ! ssh -i $pem_file ${ips[$i]} whoami 2>/dev/null | grep -q $usrname; then
        echo "SSH connection to ${ips[$i]} failed"
        exit 1
    fi
    ssh -i $pem_file ${ips[$i]} "mkdir -p autoalloc"
    echo "SSH connection to ${ips[$i]} successful"
done

# upload to master
rsync -avz -e "ssh -i $pem_file" evaluation.py hotel-reservation traces requirements.txt setup-node-non-root.sh clear.sh utils.py worker-daemon.py ${ips[0]}:autoalloc/

# setup master
if ssh -i $pem_file ${ips[0]} kubectl get nodes &> /dev/null; then
    ssh -i $pem_file ${ips[0]} kubectl get nodes
    echo "Control-plane node is already running"
else
    ssh -i $pem_file ${ips[0]} ./autoalloc/setup-node-non-root.sh master
fi

# Download from master - Modified to use sudo on remote side
mkdir -p tmp
rsync -avz -e "ssh -i $pem_file" --rsync-path="sudo rsync" ${ips[0]}:"{join-command,kube-config}" tmp/

# setup workers
for i in {1..2}; do
    rsync -avz -e "ssh -i $pem_file" setup-node-non-root.sh worker-daemon.py ${ips[$i]}:autoalloc/
    rsync -avz -e "ssh -i $pem_file" tmp/join-command tmp/kube-config ${ips[$i]}:
    ssh -i $pem_file ${ips[$i]} "./autoalloc/setup-node-non-root.sh worker autothrottle-$i"
done

# install metrics server
ssh -i $pem_file ${ips[0]} kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# set insecure TLS flag
ssh -i $pem_file ${ips[0]} "kubectl -n kube-system get deployment metrics-server -o jsonpath='{.spec.template.spec.containers[0].args}' | grep -q -- '--kubelet-insecure-tls=true'" \
    || ssh -i $pem_file ${ips[0]} "kubectl -n kube-system patch deployment metrics-server --type=json -p='[{\"op\": \"add\", \"path\": \"/spec/template/spec/containers/0/args/-\", \"value\": \"--kubelet-insecure-tls=true\"}]'"

# cleanup
rm -rf tmp