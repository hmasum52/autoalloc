#!/usr/bin/env python3
import resource
import signal
import sys

from utils import *

resource.setrlimit(resource.RLIMIT_NOFILE, (65535, 1048576))
signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

def send_notification(message):
    try:
        print(f"Notification: {message}")
        # Add your notification logic here if needed
    except Exception:
        traceback.print_exc()

def hotel_reservation():
    def deploy():
        kubectl_apply('hotel-reservation/1.json', 'hotel-reservation', 12)  # Reduced number of services
        time.sleep(180)
        # Warm up with lower RPS for smaller cluster
        time_ = datetime.datetime.utcnow().isoformat() + 'Z'
        temp_dir = pathlib.Path('tmp')/time_
        temp_dir.mkdir(parents=True, exist_ok=True)
        trace_backup = load_trace('rps.txt')
        dump_trace([50] * 15, 'rps.txt')  # Reduced from 200 to 50 RPS
        p, worker_ps = with_locust(temp_dir, 'hotel-reservation/locustfile.py', 'http://localhost:30001', 4)  # Reduced workers
        p.wait()
        for p in worker_ps:
            p.wait()
        dump_trace(trace_backup, 'rps.txt')
        time.sleep(60)

    def teardown():
        kubectl_delete('hotel-reservation/1.json', 'hotel-reservation')

    application(
        name='hotel-reservation',
        slo=0.1,  # 100ms P99 latency SLO
        nodes={
            'autothrottle-1': [
                'frontend',
                'consul'
            ],
            'autothrottle-2': [
                'search',
                'geo',
                'mongodb-geo'
            ],
            'autothrottle-3': [
                'rate',
                'recommendation',
                'mongodb-rate'
            ]
        },
        target1components={  # Core services
            'frontend',
            'search',
            'geo',
            'rate',
            'recommendation'
        },
        deploy=deploy,
        teardown=teardown,
        traces_and_targets={
            'diurnal': {  # Diurnal pattern
                'k8s-cpu': [0.7],
                'k8s-cpu-fast': [0.7],
            },
            40: {  # Constant rate of 40 RPS
                'k8s-cpu': [0.7],
                'k8s-cpu-fast': [0.8],
            },
            'noisy': {  # Noisy pattern
                'k8s-cpu': [0.6],
                'k8s-cpu-fast': [0.7],
            },
            'bursty': {  # Bursty pattern
                'k8s-cpu': [0.5],
                'k8s-cpu-fast': [0.7],
            },
        },
        trace_multiplier=0.025,  # Scaled down for smaller cluster (2.5% of original)
        aggregate_samples=200,
    )

if __name__ == '__main__':
    hotel_reservation()