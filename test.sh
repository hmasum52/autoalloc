# download from master
mkdir -p tmp
rsync -avz root@autothrottle-1:"{join-command,kube-config}" tmp/

rm -rf tmp