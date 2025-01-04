#!/bin/bash
set -ex

# check SSH connections for the 3 VMs
for i in {1..3}; do
    if [ "$(ssh root@autothrottle-$i whoami)" != root ]; then
        echo "SSH connection to autothrottle-$i failed"
        echo "Please make sure the command 'ssh root@autothrottle-$i whoami' works"
        exit 1
    fi
done

# upload to master (autothrottle-1)
rsync -avz evaluation.py hotel-reservation traces requirements.txt setup-node.sh utils.py worker-daemon.py root@autothrottle-1:

# setup master
if ssh root@autothrottle-1 kubectl get nodes &> /dev/null; then
    ssh root@autothrottle-1 kubectl get nodes
    echo "Control-plane node is already running, skipping setup."
else
    echo "Control-plane node is not running, setting up..."
    ssh root@autothrottle-1 ./setup-node.sh master
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

# install metrics server on master
ssh root@autothrottle-1 kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# set - '--kubelet-insecure-tls=true' in spec.containers.args
ssh root@autothrottle-1 "kubectl -n kube-system get deployment metrics-server -o jsonpath='{.spec.template.spec.containers[0].args}' | grep -q -- '--kubelet-insecure-tls=true'" \
    ||     ssh root@autothrottle-1 "kubectl -n kube-system patch deployment metrics-server --type=json -p='[{\"op\": \"add\", \"path\": \"/spec/template/spec/containers/0/args/-\", \"value\": \"--kubelet-insecure-tls=true\"}]'"

# cleanup
rm tmp/join-command tmp/kube-config
rmdir tmp