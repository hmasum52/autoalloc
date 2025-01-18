#!/usr/bin/env python3
import resource
import signal
import sys

from utils import *

resource.setrlimit(resource.RLIMIT_NOFILE, (65535, 1048576))
signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

TRACE_FOLDER_PATH = 'traces/resampled_1min'


# Every time a benchmark finishes, this function will be called.
# You can use this function to send a notification to your phone or do some other stuff.
def send_notification(message):
    try:
        print(message)
        # import os
        # os.system(f'timeout 60 curl ...')
        # import requests
        # requests.post(
        #     '...',
        #     json=...,
        #     timeout=60,
        # )
    except Exception:
        traceback.print_exc()

def get_log_values(path, name, trace_duration_sec, warmup_seconds, scaler_name='autothrottle', warmup_name='', target=-1):
    allocation = TimeSeries.zip_with(lambda *args: sum(args), *[v for k, v in load_cpu_limit(path).items()]) \
                .downsample_time_weighted_average(60).slice(warmup_seconds + 30, float('inf')).average()
            
    memory_allocation = TimeSeries.zip_with(lambda *args: sum(args), *[v for k, v in load_memory_limit(path).items()]) \
        .downsample_time_weighted_average(60).slice(warmup_seconds + 30, float('inf')).average()
    
    request_latency = load_request_latency(path).slice(warmup_seconds, float('inf'))
    p99_latency = request_latency.percentage(99)
    average_rps = len(request_latency) / trace_duration_sec
    log = {
        'time': datetime.datetime.utcnow().isoformat() + 'Z',
        'path': path,
        'application': name,
        'trace': 'diurnal-2',
        'scaler': scaler_name,
        'warmup': warmup_name,
        'target': target,
        'allocation': allocation,
        'memory_allocation': memory_allocation,
        'p99_latency': p99_latency,
        'average_rps': average_rps,
    }
    
    if warmup_name == '':
        # remove the warmup the log 
        log.pop('warmup')
    if target == -1:
        # remove the target the log 
        log.pop('target')
    return log
    

def application(name, slo, nodes, target1components, deploy, teardown, traces_and_targets, trace_multiplier, aggregate_samples, n_warmup=6):
    locustfile = f'{name}/locustfile.py'
    url = 'http://localhost:30001'
    namespace = name
    components = sorted(sum(nodes.values(), []))
    locust_workers = 4 # reduced from 8 to 4
    warmup_minutes = 1  # see section A.7 in the paper reduced from 3 min to 1 min
    warmup_seconds = warmup_minutes * 60
    initial_limit = 2 # number CPUs in each node
    tower_targets = [0.0, 0.02, 0.04, 0.06, 0.1, 0.15, 0.2, 0.25, 0.3]  # see section 4 in the paper
    samples = []

    # all our locustfiles are designed to read each second's RPS from rps.txt
    trace = load_trace(f'{TRACE_FOLDER_PATH}/diurnal-2.txt')
    trace_duration_sec=len(trace) # for example 3 min its 180 sec, paper: 1 hour = 3600 sec
    trace = [round(i * trace_multiplier) for i in trace]
    warmup = []
    for i in range(warmup_seconds):
        # icrease the RPS by 10% every 5 seconds
        rps = round(trace[0] * 1.1 ** ((i - warmup_seconds) / 5))  # x1.1 every 5 seconds, see section A.7 in the paper
        if rps < 1:
            rps = 1
        warmup.append(rps)
    trace = warmup + trace
    dump_trace(trace, 'rps.txt')

    # see section A.7 in the paper for the warmup process
    # 6 random exploration stage
    for i in range(n_warmup):
        path = f'data/{name}/autothrottle-warmup/a{i + 1}'
        if benchmark(
            output_dir=path,
            namespace=namespace,
            locustfile=locustfile,
            url=url,
            nodes=nodes,
            deploy=deploy,
            teardown=teardown,
            scalers={i: {'type': 'captain', 'params': (0.0, initial_limit)} for i in components},
            tower=ExploreTower(
                scaler='captain',
                targets=tower_targets,
                target1components=target1components,
                samples=[],
                warmup=warmup_minutes,
            ),
            locust_workers=locust_workers,
        ):
            log = get_log_values(path, name, trace_duration_sec, warmup_seconds, warmup_name= f'a{i+1}')
            with open('log.json', 'a') as f:
                f.write(json.dumps(log) + '\n')
            send_notification(f'{name} warmup {i + 1} / 12 finished')
        samples += load_samples(path)
    
    return
    # 6 normal leanring with a rate of 0.5
    for i in range(n_warmup):
        path = f'data/{name}/autothrottle-warmup/b{i + 1}'
        if benchmark(
            output_dir=path,
            namespace=namespace,
            locustfile=locustfile,
            url=url,
            nodes=nodes,
            deploy=deploy,
            teardown=teardown,
            scalers={i: {'type': 'captain', 'params': (0.0, initial_limit)} for i in components},
            tower=VwTower( # context-aware scaling, see section 4 in the paper
                scaler='captain',
                targets=tower_targets,
                target1components=target1components,
                slo=slo,
                samples=samples,
                explore=0.5,
                drop_samples=warmup_minutes,
                aggregate_samples=aggregate_samples,
            ),
            locust_workers=locust_workers,
        ):
            print(f"benchmark finished for {path}. Starting duirnal 2 warmup")
            log = get_log_values(path, name, trace_duration_sec, warmup_seconds, warmup_name= f'b{i+1}')
            with open('log.json', 'a') as f:
                f.write(json.dumps(log) + '\n')
            send_notification(f'{name} warmup {i + 7} / 12 finished')
        samples += load_samples(path)[warmup_minutes:]

    for trace_name, scaler_targets in traces_and_targets.items():
        # all our locustfiles are designed to read each second's RPS from rps.txt
        if isinstance(trace_name, str):
            workload_name = trace_name
            trace = load_trace(f'{TRACE_FOLDER_PATH}/{trace_name}.txt')
            trace = [round(i * trace_multiplier) for i in trace]
        elif isinstance(trace_name, int):
            workload_name = 'constant'
            trace = [trace_name] * trace_duration_sec
        else:
            raise ValueError
        warmup = []
        for i in range(warmup_seconds):
            rps = round(trace[0] * 1.1 ** ((i - warmup_seconds) / 5))  # x1.1 every 5 seconds, see section A.7 in the paper
            if rps < 1:
                rps = 1
            warmup.append(rps)
        trace = warmup + trace
        dump_trace(trace, 'rps.txt')

        path = f'data/{name}/{trace_name}/autothrottle'
        if benchmark(
            output_dir=path,
            namespace=namespace,
            locustfile=locustfile,
            url=url,
            nodes=nodes,
            deploy=deploy,
            teardown=teardown,
            scalers={i: {'type': 'captain', 'params': (0.0, initial_limit)} for i in components},
            tower=VwTower(
                scaler='captain',
                targets=tower_targets,
                target1components=target1components,
                slo=slo,
                samples=samples,
                # this is only for evaluation, see section A.7 in the paper
                # normally, 0.1 is a good value and no warmup process is needed
                explore=0.0,
                drop_samples=warmup_minutes,
                aggregate_samples=aggregate_samples,
            ),
            locust_workers=locust_workers,
        ):
            log = get_log_values(path, name, trace_duration_sec, warmup_seconds)
            allocation = log['allocation']
            p99_latency = log['p99_latency']
            
            with open('log.json', 'a') as f:
                f.write(json.dumps(log) + '\n')
            if p99_latency <= slo:
                with open('result.csv', 'a') as f:
                    f.write(f'{name},{workload_name},autothrottle,{allocation:.3f},{log["memory_allocation"]:.3f}\n')
                send_notification(f'{name} {workload_name} autothrottle result: {allocation:.3f}')
            else:
                detail = f'SLO not met. P99 latency = {p99_latency*1e3:.0f} ms. SLO = {slo*1e3:.0f} ms. Delete this path to run again: {path}'
                with open('result.csv', 'a') as f:
                    f.write(f'{name},{workload_name},autothrottle,N/A\n')
                    f.write(f'# ^ {detail}\n')
                send_notification(f'{name} {workload_name} autothrottle result: N/A. {detail}')

        for scaler, targets in scaler_targets.items():
            for target in targets:
                path = f'data/{name}/{trace_name}/{scaler}/{target}'
                if benchmark(
                    output_dir=path,
                    namespace=namespace,
                    locustfile=locustfile,
                    url=url,
                    nodes=nodes,
                    deploy=deploy,
                    teardown=teardown,
                    scalers={i: {'type': scaler, 'params': (target, initial_limit)} for i in components},
                    tower=DummyTower(),
                    locust_workers=locust_workers,
                ):
                    log = get_log_values(path, name, trace_duration_sec, warmup_seconds, scaler_name=scaler, target=target)
                    allocation = log['allocation']
                    memory_allocation = log['memory_allocation']
                    p99_latency = log['p99_latency']
                    with open('log.json', 'a') as f:
                        f.write(json.dumps(log) + '\n')
                    if p99_latency <= slo:
                        with open('result.csv', 'a') as f:
                            f.write(f'{name},{workload_name},{scaler},{allocation:.3f}, {memory_allocation:.3f}\n')
                        send_notification(f'{name} {workload_name} {scaler} result: {allocation:.3f}')
                    else:
                        detail = f'SLO not met. P99 latency = {p99_latency*1e3:.0f} ms. SLO = {slo*1e3:.0f} ms. Delete this path to run again: {path}'
                        with open('result.csv', 'a') as f:
                            f.write(f'{name},{workload_name},{scaler},N/A\n')
                            f.write(f'# ^ {detail}\n')
                        send_notification(f'{name} {workload_name} {scaler} result: N/A. {detail}')


def hotel_reservation():
    def deploy():
        print('Deploying hotel-reservation')
        kubectl_apply('hotel-reservation/1.json', 'hotel-reservation', 19)
        print('Waiting 30 sec for hotel-reservation to be ready')
        time.sleep(20) # reduced from 180
        print('hotel-reservation is ready')
        
        # Warm up by sending 2 requests per second for 15 seconds and then wait for 60 seconds
        # see section A.7 in the paper
        time_ = datetime.datetime.utcnow().isoformat() + 'Z'
        temp_dir = pathlib.Path('tmp')/time_
        temp_dir.mkdir(parents=True, exist_ok=True)
        trace_backup = load_trace('rps.txt')
        # send 20 RPS for 15 seconds to warm up
        dump_trace([20] * 15, 'rps.txt')  # Scaled down from 200 RPS to 20 RPS
        p, worker_ps = with_locust(temp_dir, 'hotel-reservation/locustfile.py', 'http://localhost:30001', 4)  # Reduced workers from 8 to 4
        p.wait()
        for p in worker_ps:
            p.wait()
        dump_trace(trace_backup, 'rps.txt')
        print('Warmup finished. Cooling down for 30 sec')
        time.sleep(20) # reduced from 60

    def teardown():
        kubectl_delete('hotel-reservation/1.json', 'hotel-reservation')

    application(
        name='hotel-reservation',
        slo=2,  # see section 5.1 in the paper - 100ms P99 latency -> increased to 2s SLO
        nodes={
            'autothrottle-2': [  # First worker node
                'frontend',
                'consul',
                'jaeger',
                'memcached-profile',
                'mongodb-profile',
                'profile',
                'memcached-rate',
                'mongodb-rate',
                'rate',
                'memcached-reserve',
                'mongodb-reservation',
                'reservation',
            ],
            'autothrottle-3': [  # Second worker node
                'geo',
                'mongodb-geo',
                'recommendation',
                'mongodb-recommendation',
                'search',
                'user',
                'mongodb-user',
            ],
        },
        target1components={  # see section A.3 in the paper - high CPU usage services
            'frontend',
            'geo',
            'profile',
            'rate',
            'reservation',
            'search',
        },
        deploy=deploy,
        teardown=teardown,
        traces_and_targets={  # see section A.6 in the paper
            'diurnal': {
                'k8s-cpu': [0.7],
                'k8s-cpu-fast': [0.7],
            },
            # 20: {  # Scaled down from 2000 RPS to 20 RPS for constant workload
            #     'k8s-cpu': [0.7],
            #     'k8s-cpu-fast': [0.8],
            # },
            # 'noisy': {
            #     'k8s-cpu': [0.6],
            #     'k8s-cpu-fast': [0.7],
            # },
            # 'bursty': {
            #     'k8s-cpu': [0.5],
            #     'k8s-cpu-fast': [0.7],
            # },
        },
        trace_multiplier=0.1,  # Scaled down from 10 to 0.1 (100x reduction)
        aggregate_samples=20,  # Reduced from 200 due to shorter duration,
        n_warmup=1,  # Reduced from 6 to {current value} due to shorter duration
    )


hotel_reservation()
