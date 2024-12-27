# 1. Backup current API server manifest
ssh autothrottle-1 cp /etc/kubernetes/manifests/kube-apiserver.yaml /tmp/

# 2. Remove API server manifest to stop the server
ssh autothrottle-1 rm /etc/kubernetes/manifests/kube-apiserver.yaml

# 3. Delete existing certificates
ssh autothrottle-1 rm /etc/kubernetes/pki/apiserver.{crt,key}

# 4. Regenerate certificates with public IP
ssh autothrottle-1 kubeadm init phase certs apiserver --apiserver-cert-extra-sans=4.213.52.192

# 5. Restore API server manifest
ssh autothrottle-1 cp /tmp/kube-apiserver.yaml /etc/kubernetes/manifests/

# 6. Restart kubelet
ssh autothrottle-1 systemctl restart kubelet