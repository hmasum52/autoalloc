#!/usr/bin/env python3
import collections
import json
import pathlib
import socket
import statistics
import subprocess
import time
import threading
import traceback

# <changes>
with open('./worker-daemon.log', 'w') as f:
    pass

def log(*args):
    with open('./worker-daemon.log', 'a') as f:
        current_date_time = time.strftime("%H:%M:%S", time.localtime())
        f.write(f'{current_date_time} ')
        f.write(' '.join(map(str, args)))
        f.write('\n')
        print(*args)

CPU_USASGE_METRIC = 'cpuacct.usage'
CPU_STAT_METRIC = 'cpu.stat'

MEMORY_USAGE_METRIC = 'memory.usage_in_bytes'
MEMORY_LIMIT_METRIC = 'memory.limit_in_bytes'
MEMORY_STAT_METRIC = 'memory.stat'

def get_memory_stats(pod_map, name):
    # Read memory.stat file from cgroup
    stat_path(pod_map, name, MEMORY_STAT_METRIC).read_text().splitlines()
    # Track key metrics:
    # - total_inactive_file (clean cache that can be reclaimed)
    # - total_active_file (dirty cache that needs to be written)
    # - unevictable (pinned memory)
    # - pgfault (minor page faults)
    # - pgmajfault (major page faults requiring disk I/O)
    
def calculate_memory_pressure(stats):
    """Calculate memory pressure from stats"""
    # Memory pressure could be calculated as:
    # - High page fault rate 
    # - High ratio of used memory to limit
    # - Presence of OOM events
    pressure = (stats['pgmajfault'] * 0.7 + 
               stats[MEMORY_USAGE_METRIC] / stats[MEMORY_LIMIT_METRIC] * 0.3)
    return pressure
# </changes>

def get_pod_map(namespace, components):
    name_to_uid = {}
    p = subprocess.run(['kubectl', 'get', 'pods', f'-n={namespace}',
        r'-o=jsonpath={range .items[*]}{.metadata.uid} {.metadata.name}{"\n"}{end}'],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True, check=True)
    for i in p.stdout.splitlines():
        uid, name = i.split()
        name = name.rsplit('-', 2)[0]
        if name in components:
            assert name not in name_to_uid
            name_to_uid[name] = uid

    uid_to_qos = {}
    cgroup = pathlib.Path('/sys/fs/cgroup')
    for qos in ['guaranteed', 'burstable', 'besteffort']:
        d = cgroup/f'cpu/kubepods.slice/kubepods-{qos}.slice'
        p = f'kubepods-{qos}-pod'
        s = '.slice'
        for i in d.glob(f'{p}*{s}'):
            uid = i.name[len(p):-len(s)].replace('_', '-')
            uid_to_qos[uid] = qos

    pod_map = {}
    for name in components:
        uid = name_to_uid[name]
        try:
            qos = uid_to_qos[uid]
        except KeyError:
            pass
        else:
            pod_map[name] = qos, uid
    return pod_map


def stat_path(pod_map, name, stat):
    qos, uid = pod_map[name]
    family, _, name = stat.partition('.')
    slices = f'kubepods.slice/kubepods-{qos}.slice/kubepods-{qos}-pod{uid.replace("-", "_")}.slice'
    return pathlib.Path(f'/sys/fs/cgroup/{family}/{slices}/{family}.{name}')


def set_cpu_limit(pod_map, name, limit, period=0.1):
    period_us = round(period * 1e6)
    assert 1000 <= period_us <= 1000000
    if limit is None:
        quota_us = -1
    else:
        quota_us = round(limit * period_us)
        assert quota_us >= 1000
    stat_path(pod_map, name, 'cpu.cfs_period_us').write_text(str(period_us))
    stat_path(pod_map, name, 'cpu.cfs_quota_us').write_text(str(quota_us))

# <changes>
def set_memory_limit(pod_map, name, limit_mb):
    """Set memory limit in MB"""
    if limit_mb is None:
        # No limit
        limit_bytes = 512 * 1024 * 1024  # 512MB
    else:
        limit_bytes = int(limit_mb * 1024 * 1024)
    log(f'{name}: setting memory limit to {limit_bytes} bytes ({limit_mb}MB)')
    stat_path(pod_map, name, MEMORY_LIMIT_METRIC).write_text(str(limit_bytes))
    # read back the limit
    log(f'{name}: memory limit set to {stat_path(pod_map, name, MEMORY_LIMIT_METRIC).read_text()} bytes')
# </changes>

class ConstScaler:
    def __init__(self, limit):
        self.name = 'const'
        self.limit = limit

    def __call__(self, t, stats):
        print(f"calling {self.name} scaler")
        return self.limit, None

    def update(self, limit):
        self.limit = limit


class K8sCPUScalerBase:
    def __init__(self, period, stabilization, target, initial_limit):
        self.name = 'k8s-cpu'
        self.period = period
        self.target = target
        self.limit = initial_limit
        self.recommend_len = stabilization // period
        self.recommendations = []

        self.last_t = None
        self.last_stats = None

    def __call__(self, t, stats):
        print(f"calling {self.name} scaler")
        if self.last_t is None:
            self.last_t = t
            self.last_stats = stats
            return self.limit
        if t < self.last_t + self.period - 0.0001:
            return self.limit
        usage = (stats['cpu_usage'] - self.last_stats['cpu_usage']) / (t - self.last_t)
        self.scale(usage)
        self.last_t = t
        self.last_stats = stats
        return self.limit, None

    def scale(self, usage):
        self.recommendations.append(usage / self.target)
        if len(self.recommendations) > self.recommend_len:
            self.recommendations.pop(0)
        self.limit = max(self.recommendations)

    def update(self, target):
        self.target = target


class K8sCPUScaler(K8sCPUScalerBase):
    def __init__(self, target, initial_limit=1):
        self.name = 'k8s-cpu' # change
        super().__init__(period=15, stabilization=300, target=target, initial_limit=initial_limit)


class K8sCPUFastScaler(K8sCPUScalerBase):
    def __init__(self, target, initial_limit=1):
        self.name = 'k8s-cpu-fast' #change
        super().__init__(period=1, stabilization=20, target=target, initial_limit=initial_limit)


class CaptainScaler:
    def __init__(self, target, initial_limit=1):
        self.name = 'captain' # change
        # read-only parameters
        self.target = target
        self.period = 1

        # state
        self.limit = initial_limit
        self.last_limit = initial_limit
        self.throttled_history = [0 for _ in range(int(10 * self.period))]
        self.usage_history = [0.0 for _ in range(50)]
        self.margin = 3
        self.scale_down_cd = 0
        self.last_scale_down = False

        self.last_t = None
        self.last_stats = None
        self.last_scale_t = None

    def __call__(self, t, stats):
        if self.last_t is None:
            self.last_t = t
            self.last_stats = stats
            self.last_scale_t = t
            return self.limit

        new_throttled = stats['cpu_stat.nr_throttled'] - self.last_stats['cpu_stat.nr_throttled']
        self.throttled_history.append(new_throttled)
        self.throttled_history.pop(0)
        new_usage = (stats['cpu_usage'] - self.last_stats['cpu_usage']) / (t - self.last_t)
        self.usage_history.append(new_usage)
        self.usage_history.pop(0)
        self.last_t = t
        self.last_stats = stats
        throttled_rate = statistics.mean(self.throttled_history)
        if throttled_rate > 3 * self.target and self.last_scale_down:
            self.limit = 2 * self.last_limit - self.limit
            self.margin += (throttled_rate - self.target)
            self.throttled_history = [0 for _ in range(int(10 * self.period))]
            self.last_scale_down = False

        if t < self.last_scale_t + self.period - 0.0001:
            return self.limit
        self.last_limit = self.limit
        throttled_rate = statistics.mean(self.throttled_history)
        usage_max = max(self.usage_history)
        usage_std = statistics.stdev(self.usage_history)

        self.margin += (throttled_rate - self.target)
        self.margin = max(0, self.margin)
        self.last_scale_down = False
        if throttled_rate > 3 * self.target:
            self.limit *= 1 + (throttled_rate - 3 * self.target)
        else:
            usage_limit = usage_max + usage_std * self.margin
            if usage_limit <= self.limit * 0.9 and self.scale_down_cd == 0:
                self.limit = max(self.limit * 0.5, usage_limit)
                self.last_scale_down = True
        self.throttled_history = [0 for _ in range(int(10 * self.period))]
        self.limit = max(0.01, self.limit)
        self.last_scale_t = t
        stats['captain.margin'] = self.margin
        return self.limit

    def update(self, target):
        self.target = target

# <changes>
class CaptainScalerWithMemoryUsage(CaptainScaler):
    def __init__(self, target, initial_limit=1, initial_mem_limit=256):
        super().__init__(target, initial_limit)
        # Memory parameters
        self.name = 'captain_with_memory'
        self.memory_limit = initial_mem_limit
        self.memory_high_watermark = 0.9  # 90% usage triggers scale up
        self.memory_low_watermark = 0.7   # 70% usage allows scale down
        self.memory_headroom = 1.3        # Keep 30% extra capacity
        self.min_memory = 64            # Minimum 1GB memory

    def __call__(self, t, stats):
        print(f"calling {self.name} scaler")
        cpu_limit = super().__call__(t, stats)
        log(f'captain_scaler: cpu limit {cpu_limit}')
        
        # Memory scaling
        memory_usage = stats['memory_usage']
        memory_limit = stats['memory_limit']
        log(f'captain_scaler: memory usage {memory_usage}')
        log(f'captain_scaler: pod memory limit {memory_limit}')
        log(f'captain_scaler: scaler memory limit {self.memory_limit}')
        memory_usage_ratio = memory_usage / self.memory_limit
        log(f'captain_scaler: memory usage ratio {memory_usage_ratio}')
        
        if memory_usage_ratio > self.memory_high_watermark:
            self.memory_limit *= 1.2  # Increase by 20%
        elif memory_usage_ratio < self.memory_low_watermark:
            proposed_limit = memory_usage * self.memory_headroom
            if proposed_limit < self.memory_limit:
                self.memory_limit = max(self.min_memory, proposed_limit)
        log(f'captain_scaler: new memory limit {self.memory_limit}')      
        return cpu_limit, self.memory_limit
# </changes>
  
def init_scaler(data):
    return {
        'const': ConstScaler,
        'k8s-cpu-fast': K8sCPUFastScaler,
        'k8s-cpu': K8sCPUScaler,
        'captain': CaptainScalerWithMemoryUsage,
    }[data['type']](*data['params'])


def run(control, namespace, components, scalers):
    pod_map = get_pod_map(namespace, components)

    limits = {}
    memory_limits = {} # <changes>

    for name in scalers:
        assert name in components
    for name in components:
        limits[name] = None
        set_cpu_limit(pod_map, name, None)
        # <changes>
        memory_limits[name] = None
        set_memory_limit(pod_map, name, 256)
        # </changes>

    files = {}
    for name in components:
        files[name, CPU_USASGE_METRIC] = stat_path(pod_map, name, CPU_USASGE_METRIC).open()
        files[name, CPU_STAT_METRIC] = stat_path(pod_map, name, CPU_STAT_METRIC).open()
        
        # Memory stats
        # <mem>
        files[name, MEMORY_USAGE_METRIC] = stat_path(pod_map, name, MEMORY_USAGE_METRIC).open()
        files[name, MEMORY_LIMIT_METRIC] = stat_path(pod_map, name, MEMORY_LIMIT_METRIC).open()
        # </mem>

    log(f'running for {namespace} {components} {files}')

    monotonic_base = time.time() - time.perf_counter()

    stats_history = collections.defaultdict(list)
    control['stats'] = stats_history

    stats_current = collections.defaultdict(list)
    control['stats_current'] = stats_current

    late_end_time = 0
    while True:
        t = time.perf_counter()
        tt = (0.097 - t) * 1000 % 100 / 1000
        t += tt
        time.sleep(tt)
        if control['stop']:
            break

        stats = collections.defaultdict(dict)
        for name in components:
            # CPU stats
            files[name, CPU_USASGE_METRIC].seek(0)
            stats[name]['cpu_usage'] = files[name, CPU_USASGE_METRIC].read()
            files[name, CPU_STAT_METRIC].seek(0)
            for line in files[name, CPU_STAT_METRIC].read().splitlines():
                k, v = line.split()
                stats[name][f'cpu_stat.{k}'] = v
            
            # <mem>
            # Memory stats
            files[name, MEMORY_USAGE_METRIC].seek(0)
            stats[name]['memory_usage'] = int(files[name, MEMORY_USAGE_METRIC].read().strip()) / (1024 * 1024)  # MB
            
            files[name, MEMORY_LIMIT_METRIC].seek(0)
            # memory limit can undefined and a big number 9223372036854771712
            mem_limit = files[name, MEMORY_LIMIT_METRIC].read().strip()
            if mem_limit == '9223372036854771712':
                stats[name]['memory_limit'] = 256  # MB
            else: 
                stats[name]['memory_limit'] = int(int(mem_limit) / (1024 * 1024))  # MB
            log(f'{name}: memory limit {stats[name]["memory_limit"]}MB')
            
            # </mem>

        end_time = time.perf_counter()
        if end_time > t + (-t * 1000 % 100 / 1000):
            late_end_time += 1

        for name in components:
            stats[name]['cpu_usage'] = int(stats[name]['cpu_usage']) / 1e9
            stats[name]['cpu_stat.nr_periods'] = int(stats[name]['cpu_stat.nr_periods'])
            stats[name]['cpu_stat.nr_throttled'] = int(stats[name]['cpu_stat.nr_throttled'])
            stats[name]['cpu_stat.throttled_time'] = int(stats[name]['cpu_stat.throttled_time']) / 1e9

        if control['update']:
            for k, v in control['update'].items():
                if k in scalers:
                    scalers[k].update(*v)
            control['update'] = {}

        for name, scaler in scalers.items():
            limit, memory_limit = scaler(t, stats[name])   # <mem>         
            log(f'{name}: scaler returned cpu limit {limit}, memory limit: {memory_limit}')
            if limit is not None:
                limit = max(0.01, limit)
                if limits[name] is not None:
                    if abs(limit - limits[name]) < 0.00001:
                        limit = limits[name]
            if limit != limits[name]:
                limits[name] = limit
                set_cpu_limit(pod_map, name, limit)
            
            # <mem>
            if memory_limit is not None:
                memory_limit = max(64, memory_limit)  # Minimum 128MB
                if memory_limits[name] is not None:
                    if abs(memory_limit - memory_limits[name]) >= 1:  # 1MB difference threshold
                        memory_limits[name] = memory_limit
                        log(f'{name}: (1)setting new memory limit to {memory_limit}MB')
                        set_memory_limit(pod_map, name, memory_limit)
            if memory_limit != memory_limits[name]:
                memory_limits[name] = memory_limit
                log(f'{name}: (2)setting new memory limit to {memory_limit}MB')
                set_memory_limit(pod_map, name, memory_limit)
            # </mem>
                
            stats[name]['scaler.limit'] = limits[name]
            stats[name]['scaler.memory_limit'] = memory_limits[name] # <mem>
            if memory_limit is not None: # <mem>
                log(f'[new*] {name}: cpu limit {limit}, memory limit: {memory_limit}')

        for name in stats:
            stats_history[name].append((t + monotonic_base, stats[name]))
            stats_current[name].append((t + monotonic_base, stats[name]))

    if late_end_time:
        print(f'late end time: {late_end_time}')

    for f in files.values():
        f.close()


def process_client(client_socket):
    line = client_socket.readline()
    data = json.loads(line)
    assert data['method'] == 'start'
    control = {
        'stop': False,
        'socket': client_socket,
        'update': {},
    }
    scalers = {k: init_scaler(v) for k, v in data['scalers'].items()}
    thread = threading.Thread(target=run, args=(control, data['namespace'], data['components'], scalers))
    thread.start()
    client_socket.write(json.dumps({'ok': True}) + '\n')
    client_socket.flush()
    try:
        while True:
            line = client_socket.readline()
            data = json.loads(line)
            if data['method'] == 'update':
                control['update'] = data['update']
                client_socket.write(json.dumps({'ok': True}) + '\n')
                client_socket.flush()
                continue
            elif data['method'] == 'stats':
                stats = {}
                for i in control['stats_current']:
                    stats[i] = control['stats_current'][i]
                    control['stats_current'][i] = []
                client_socket.write(json.dumps({
                    'ok': True,
                    'stats': stats,
                }) + '\n')
                client_socket.flush()
                continue
            elif data['method'] == 'stop':
                control['stop'] = True
                thread.join()
                client_socket.write(json.dumps({
                    'ok': True,
                    'stats': control['stats'],
                }) + '\n')
                client_socket.flush()
                client_socket.close()
                break
            raise ValueError(f'unknown method: {data["method"]}')
    except Exception:
        traceback.print_exc()
        control['stop'] = True
        thread.join()
        client_socket.close()
        print('thread stopped')
        print()


def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('0.0.0.0', 12198))
    server_socket.listen()
    print('listening')
    while True:
        client_socket, address = server_socket.accept()
        print(f'accepted connection from {address}')
        process_client(client_socket.makefile('rw'))
        print('finished')


if __name__ == '__main__':
    main()
