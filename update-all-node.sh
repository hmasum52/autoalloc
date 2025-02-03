pem_file="dr_adnan_keypair.pem"
declare -a ips=(
    [0]=ubuntu@10.10.0.158
    [1]=ubuntu@10.10.2.172
    [2]=ubuntu@10.10.1.219
)

# Upload files to the main node
rsync -avz -e "ssh -i $pem_file" evaluation.py hotel-reservation traces requirements.txt setup-node-non-root.sh utils.py worker-daemon.py ${ips[0]}:autoalloc/

for i in {1..2}; do
    # upload to worker
    echo "Uploading to ${ips[$i]}"
    rsync -avz -e "ssh -i $pem_file" test.py worker-daemon.py ${ips[$i]}:autoalloc/
    
    # kill existing worker-daemon tmux session
    echo "Killing existing worker-daemon tmux session on autothrottle-$i"
    ssh -i $pem_file ${ips[i]} "tmux ls && tmux kill-session -t worker-daemon || true && tmux ls"
    echo "Killed..."

    # we need sudo kube config for the worker as running with sudo doesn't have access to the user kube config
    exists=$(ssh -i $pem_file ${ips[i]} "sudo ls /root/.kube/config || true")
    if [ -z "$exists" ]; then
        echo "Kube config doesn't exist on worker root. Copying..."
        ssh -i $pem_file ${ips[i]} "sudo mkdir -p /root/.kube"
        ssh -i $pem_file ${ips[i]} "sudo cp /home/ubuntu/.kube/config /root/.kube/config"
        ssh -i $pem_file ${ips[i]} "sudo chown -R root:root /root/.kube"
    else
        echo "Kube config already exists on worker root"
    fi

    # Make worker-daemon.py executable
    ssh -i $pem_file ${ips[i]} "chmod +x ./autoalloc/worker-daemon.py"

    # Setup sudo permission for the specific script
    ssh -i $pem_file ${ips[i]} "echo 'ubuntu ALL=(ALL) NOPASSWD: /home/ubuntu/autoalloc/worker-daemon.py' | sudo tee /etc/sudoers.d/worker-daemon"
    
    # Make sure the sudoers.d file has correct permissions
    ssh -i $pem_file ${ips[i]} "sudo chmod 440 /etc/sudoers.d/worker-daemon"

    # setup worker with sudo
    echo "Setting up worker-daemon on autothrottle-$i"
    ssh -i $pem_file ${ips[i]} "tmux new-session -d -s worker-daemon 'sudo python3 ./autoalloc/worker-daemon.py' && tmux set-option -t worker-daemon remain-on-exit on && tmux ls"
    echo "Done..."
done