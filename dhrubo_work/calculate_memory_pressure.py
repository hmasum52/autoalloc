import time
import datetime


def read_memory_pressure():
    with open("/proc/pressure/memory", "r") as f:
        lines = f.readlines()

    pressure_stats = {}
    for line in lines:
        kind, stats = line.strip().split(" ", 1)
        stats_dict = {}
        for stat in stats.split():
            key, value = stat.split("=")
            stats_dict[key] = float(value)
        pressure_stats[kind] = stats_dict

    return pressure_stats


def calculate_pressure_ratio(window_size=10):  # window size in seconds
    print(f"Monitoring memory pressure over {window_size} second windows...")
    print("Time                 Some    Full    Total")
    print("-" * 50)

    while True:
        start_pressure = read_memory_pressure()
        time.sleep(window_size)
        end_pressure = read_memory_pressure()

        # Calculate stall time differences
        some_stall = end_pressure["some"]["total"] - start_pressure["some"]["total"]
        full_stall = end_pressure["full"]["total"] - start_pressure["full"]["total"]

        # Normalize to get ratio between 0 and 1
        some_ratio = min(
            1.0, some_stall / (window_size * 1000)
        )  # PSI values are in microseconds
        full_ratio = min(1.0, full_stall / (window_size * 1000))
        total_ratio = (some_ratio + full_ratio) / 2

        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{current_time}  {some_ratio:.3f}  {full_ratio:.3f}  {total_ratio:.3f}")


if __name__ == "__main__":
    try:
        calculate_pressure_ratio()
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")
    except FileNotFoundError:
        print(
            "Error: Cannot access /proc/pressure/memory. Make sure you're running on Linux with PSI enabled."
        )
