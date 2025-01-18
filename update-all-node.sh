rsync -avz evaluation.py hotel-reservation traces requirements.txt setup-node.sh utils.py worker-daemon.py root@autothrottle-1:

for i in {2..3}; do
    # upload to worker
    rsync -avz worker-daemon.py root@autothrottle-$i:
    
    # kill existing worker-daemon tmux session
    echo "Killing existing worker-daemon tmux session on autothrottle-$i"
    ssh root@autothrottle-$i "tmux ls && tmux kill-session -t worker-daemon || true && tmux ls"
    echo "Killed..."

    # setup worker
    echo "Setting up worker-daemon on autothrottle-$i"
    ssh root@autothrottle-$i "tmux new-session -d -s worker-daemon './worker-daemon.py' && tmux set-option -t worker-daemon remain-on-exit on && tmux ls"
    echo "Done..."
done