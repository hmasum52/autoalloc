from locust import FastHttpUser, LoadTestShape, task, events
import locust.stats
import random
import logging
import time
import json
from pathlib import Path

# Modify stats collection intervals for smaller workload
locust.stats.CONSOLE_STATS_INTERVAL_SEC = 60  # Reduced from 600
locust.stats.HISTORY_STATS_INTERVAL_SEC = 30  # Reduced from 60
locust.stats.CSV_STATS_INTERVAL_SEC = 30      # Reduced from 60
locust.stats.CSV_STATS_FLUSH_INTERVAL_SEC = 30 # Reduced from 60
locust.stats.CURRENT_RESPONSE_TIME_PERCENTILE_WINDOW = 30 # Reduced from 60

random.seed(time.time())
logging.basicConfig(level=logging.INFO)

def get_user():
    # Reduce user pool size for smaller workload
    user_id = random.randint(0, 100)  # Reduced from 500
    user_name = 'Cornell_' + str(user_id)
    password = str(user_id) * 10
    return user_name, password

mean_iat = 1  # seconds between requests

request_log_file = open('request.log', 'a')

class HotelReservationUser(FastHttpUser):
    def wait_time(self):
        return random.expovariate(lambd=1/mean_iat)

    @events.request.add_listener
    def on_request(response_time, context, **kwargs):
        request_log_file.write(json.dumps({
            'time': time.perf_counter(),
            'latency': response_time / 1e3,
            'context': context,
        }) + '\n')

    # Maintain same ratios but simplify date ranges
    @task(600)
    def search_hotel(self):
        in_date = random.randint(1, 15)
        out_date = random.randint(in_date + 1, 20)

        in_date = f"2024-04-{str(in_date).zfill(2)}"
        out_date = f"2024-04-{str(out_date).zfill(2)}"

        # Reduce geographic area for more cache hits
        lat = 38.0235 + (random.randint(0, 100) - 50)/1000.0
        lon = -122.095 + (random.randint(0, 100) - 50)/1000.0

        path = f'/hotels?inDate={in_date}&outDate={out_date}&lat={lat}&lon={lon}'
        self.client.get(path, name='search_hotel', context={'type': 'search_hotel'})

    @task(390)
    def recommend(self):
        req_param = random.choice(['dis', 'rate', 'price'])
        
        # Reduce geographic area
        lat = 38.0235 + (random.randint(0, 100) - 50)/1000.0
        lon = -122.095 + (random.randint(0, 100) - 50)/1000.0

        path = f'/recommendations?require={req_param}&lat={lat}&lon={lon}'
        self.client.get(path, name='recommend', context={'type': 'recommend'})

    @task(5)
    def reserve(self):
        in_date = random.randint(1, 15)
        out_date = in_date + random.randint(1, 3)  # Shorter stays

        in_date = f"2024-04-{str(in_date).zfill(2)}"
        out_date = f"2024-04-{str(out_date).zfill(2)}"

        lat = 38.0235 + (random.randint(0, 100) - 50)/1000.0
        lon = -122.095 + (random.randint(0, 100) - 50)/1000.0

        # Reduce hotel range
        hotel_id = str(random.randint(1, 20))  # Reduced from 80
        user_name, password = get_user()

        path = f'/reservation?inDate={in_date}&outDate={out_date}&lat={lat}&lon={lon}&hotelId={hotel_id}&customerName={user_name}&username={user_name}&password={password}&number=1'
        self.client.post(path, name='reserve', context={'type': 'reserve'})

    @task(5)
    def user_login(self):
        user_name, password = get_user()
        path = f'/user?username={user_name}&password={password}'
        self.client.get(path, name='user_login', context={'type': 'user_login'})

class CustomShape(LoadTestShape):
    """
    A custom load shape that provides three patterns:
    1. Constant: 40 RPS
    2. Diurnal: 20-60 RPS following a sine wave
    3. Bursty: Base 30 RPS with spikes to 60 RPS
    """
    time_limit = 3600  # 1 hour test
    pattern = "diurnal"  # Change this to "constant" or "bursty" for different patterns

    def tick(self):
        run_time = self.get_run_time()
        
        if run_time < self.time_limit:
            if self.pattern == "constant":
                return (40, 10)  # (users, spawn_rate)
            
            elif self.pattern == "diurnal":
                # Sine wave between 20 and 60 RPS
                slope = (math.sin(run_time * math.pi / 1800) + 1) / 2  # Full cycle every 1 hour
                users = int(20 + slope * 40)
                return (users, 10)
            
            elif self.pattern == "bursty":
                # Base load of 30 RPS with spikes to 60 RPS every 5 minutes
                if run_time % 300 < 30:  # Spike for 30 seconds every 5 minutes
                    return (60, 10)
                return (30, 10)
        
        return None