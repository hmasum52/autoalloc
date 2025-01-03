#!/usr/bin/env python3
import resource
import signal
import sys

from utils import *

resource.setrlimit(resource.RLIMIT_NOFILE, (65535, 1048576))
signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))


# Every time a benchmark finishes, this function will be called.
# You can use this function to send a notification to your phone or do some other stuff.
def send_notification(message):
    try:
        pass
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


def application(name, slo, nodes, target1components, deploy, teardown, traces_and_targets, trace_multiplier, aggregate_samples):
    locustfile = f'{name}/locustfile.py'
    url = 'http://localhost:30001'
    namespace = name
    components = sorted(sum(nodes.values(), []))
    locust_workers = 8
    warmup_minutes = 3  # see section A.7 in the paper
    warmup_seconds = warmup_minutes * 60
    initial_limit = 32
    tower_targets = [0.0, 0.02, 0.04, 0.06, 0.1, 0.15, 0.2, 0.25, 0.3]  # see section 4 in the paper
    samples = []

    # all our locustfiles are designed to read each second's RPS from rps.txt
    trace = load_trace('traces/diurnal-2.txt')
    trace = [round(i * trace_multiplier) for i in trace]
    warmup = []
    for i in range(warmup_seconds):
        rps = round(trace[0] * 1.1 ** ((i - warmup_seconds) / 5))  # x1.1 every 5 seconds, see section A.7 in the paper
        if rps < 1:
            rps = 1
        warmup.append(rps)
    trace = warmup + trace
    dump_trace(trace, 'rps.txt')

    # see section A.7 in the paper for the warmup process
    for i in range(6):
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
            allocation = TimeSeries.zip_with(lambda *args: sum(args), *[v for k, v in load_cpu_limit(path).items()]) \
                .downsample_time_weighted_average(60).slice(warmup_seconds + 30, float('inf')).average()
            request_latency = load_request_latency(path).slice(warmup_seconds, float('inf'))
            p99_latency = request_latency.percentage(99)
            average_rps = len(request_latency) / 3600
            log = {
                'time': datetime.datetime.utcnow().isoformat() + 'Z',
                'path': path,
                'application': name,
                'trace': 'diurnal-2',
                'scaler': 'autothrottle',
                'warmup': f'a{i + 1}',
                'allocation': allocation,
                'p99_latency': p99_latency,
                'average_rps': average_rps,
            }
            with open('log.json', 'a') as f:
                f.write(json.dumps(log) + '\n')
            send_notification(f'{name} warmup {i + 1} / 12 finished')
        samples += load_samples(path)
    for i in range(6):
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
            allocation = TimeSeries.zip_with(lambda *args: sum(args), *[v for k, v in load_cpu_limit(path).items()]) \
                .downsample_time_weighted_average(60).slice(warmup_seconds + 30, float('inf')).average()
            request_latency = load_request_latency(path).slice(warmup_seconds, float('inf'))
            p99_latency = request_latency.percentage(99)
            average_rps = len(request_latency) / 3600
            log = {
                'time': datetime.datetime.utcnow().isoformat() + 'Z',
                'path': path,
                'application': name,
                'trace': 'diurnal-2',
                'scaler': 'autothrottle',
                'warmup': f'b{i + 1}',
                'allocation': allocation,
                'p99_latency': p99_latency,
                'average_rps': average_rps,
            }
            with open('log.json', 'a') as f:
                f.write(json.dumps(log) + '\n')
            send_notification(f'{name} warmup {i + 7} / 12 finished')
        samples += load_samples(path)[warmup_minutes:]

    for trace_name, scaler_targets in traces_and_targets.items():
        # all our locustfiles are designed to read each second's RPS from rps.txt
        if isinstance(trace_name, str):
            workload_name = trace_name
            trace = load_trace(f'traces/{trace_name}.txt')
            trace = [round(i * trace_multiplier) for i in trace]
        elif isinstance(trace_name, int):
            workload_name = 'constant'
            trace = [trace_name] * 3600
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
            allocation = TimeSeries.zip_with(lambda *args: sum(args), *[v for k, v in load_cpu_limit(path).items()]) \
                .downsample_time_weighted_average(60).slice(warmup_seconds + 30, float('inf')).average()
            request_latency = load_request_latency(path).slice(warmup_seconds, float('inf'))
            p99_latency = request_latency.percentage(99)
            average_rps = len(request_latency) / 3600
            log = {
                'time': datetime.datetime.utcnow().isoformat() + 'Z',
                'path': path,
                'application': name,
                'trace': trace_name,
                'scaler': 'autothrottle',
                'allocation': allocation,
                'p99_latency': p99_latency,
                'average_rps': average_rps,
            }
            with open('log.json', 'a') as f:
                f.write(json.dumps(log) + '\n')
            if p99_latency <= slo:
                with open('result.csv', 'a') as f:
                    f.write(f'{name},{workload_name},autothrottle,{allocation:.2f}\n')
                send_notification(f'{name} {workload_name} autothrottle result: {allocation:.2f}')
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
                    allocation = TimeSeries.zip_with(lambda *args: sum(args), *[v for k, v in load_cpu_limit(path).items()]) \
                        .downsample_time_weighted_average(60).slice(warmup_seconds + 30, float('inf')).average()
                    request_latency = load_request_latency(path).slice(warmup_seconds, float('inf'))
                    p99_latency = request_latency.percentage(99)
                    average_rps = len(request_latency) / 3600
                    log = {
                        'time': datetime.datetime.utcnow().isoformat() + 'Z',
                        'path': path,
                        'application': name,
                        'trace': trace_name,
                        'scaler': scaler,
                        'target': target,
                        'allocation': allocation,
                        'p99_latency': p99_latency,
                        'average_rps': average_rps,
                    }
                    with open('log.json', 'a') as f:
                        f.write(json.dumps(log) + '\n')
                    if p99_latency <= slo:
                        with open('result.csv', 'a') as f:
                            f.write(f'{name},{workload_name},{scaler},{allocation:.2f}\n')
                        send_notification(f'{name} {workload_name} {scaler} result: {allocation:.2f}')
                    else:
                        detail = f'SLO not met. P99 latency = {p99_latency*1e3:.0f} ms. SLO = {slo*1e3:.0f} ms. Delete this path to run again: {path}'
                        with open('result.csv', 'a') as f:
                            f.write(f'{name},{workload_name},{scaler},N/A\n')
                            f.write(f'# ^ {detail}\n')
                        send_notification(f'{name} {workload_name} {scaler} result: N/A. {detail}')


def hotel_reservation():
    def deploy():
        kubectl_apply('hotel-reservation/1.json', 'hotel-reservation', 19)
        time.sleep(180)
        # warm up by sending 200 requests per second for 15 seconds and then wait for 60 seconds
        # see section A.7 in the paper
        time_ = datetime.datetime.utcnow().isoformat() + 'Z'
        temp_dir = pathlib.Path('tmp')/time_
        temp_dir.mkdir(parents=True, exist_ok=True)
        trace_backup = load_trace('rps.txt')
        dump_trace([200] * 15, 'rps.txt')
        p, worker_ps = with_locust(temp_dir, 'hotel-reservation/locustfile.py', 'http://localhost:30001', 8)
        p.wait()
        for p in worker_ps:
            p.wait()
        dump_trace(trace_backup, 'rps.txt')
        time.sleep(60)

    def teardown():
        kubectl_delete('hotel-reservation/1.json', 'hotel-reservation')

    application(
        name='hotel-reservation',
        slo=0.1,  # see section 5.1 in the paper
        nodes={
            'autothrottle-2': [
                'frontend',
            ],
            'autothrottle-3': [
                'memcached-reserve',
                'mongodb-recommendation',
                'mongodb-reservation',
                'recommendation',
                'reservation',
            ],
            'autothrottle-4': [
                'geo',
                'mongodb-geo',
                'mongodb-user',
                'search',
                'user',
            ],
            'autothrottle-5': [
                'memcached-profile',
                'memcached-rate',
                'mongodb-profile',
                'mongodb-rate',
                'profile',
                'rate',
            ],
        },
        target1components={  # see section A.3 in the paper
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
            2000: {
                'k8s-cpu': [0.7],
                'k8s-cpu-fast': [0.8],
            },
            'noisy': {
                'k8s-cpu': [0.6],
                'k8s-cpu-fast': [0.7],
            },
            'bursty': {
                'k8s-cpu': [0.5],
                'k8s-cpu-fast': [0.7],
            },
        },
        trace_multiplier=10,
        aggregate_samples=200,
    )

hotel_reservation()
