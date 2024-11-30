# Memory Pressure

To quantify memory pressure in our system, we developed a ratio-based metric that captures the temporal impact of memory constraints on service performance. The Memory Pressure Ratio (MPR) is defined as:

`MPR = Time spent in memory stall / Total observation window`

where:

- Time spent in memory stall represents the cumulative duration during which processes experience memory access delays
- Total observation window is the overall measurement period

We collect memory stall information through Linux's Pressure Stall Information (PSI) interface, which provides high-resolution data about memory subsystem congestion. PSI metrics are accessed via /proc/pressure/memory, offering both partial ("some") and complete ("full") stall measurements.
The ratio yields values between 0 and 1, where:

- 0 indicates no memory pressure (optimal performance)
- 1 indicates continuous memory stalls (severe degradation)

Itermediate values represent the proportion of time the system spent handling memory pressure

This metric was chosen for three key characteristics:

Temporal representation: Unlike snapshot-based metrics (e.g., free memory), MPR captures the dynamic impact of memory pressure over time
Performance correlation: The ratio directly relates to service degradation by measuring actual stall time
Normalization: The metric is normalized by time window, enabling comparison across different observation periods

The measurement window can be adjusted based on the monitoring requirements, typically ranging from seconds for fine-grained analysis to hours for trend assessment. In our implementation, we used a 60-second window to balance measurement granularity with operational overhead.

# Measuring Memory Pressure on Ubuntu:

```bash
mmk@mmk:~$ cat /proc/pressure/memory
some avg10=0.00 avg60=0.00 avg300=0.00 total=77503
full avg10=0.00 avg60=0.00 avg300=0.00 total=76923
```

The output from `/proc/pressure/memory` provides information about **memory pressure** on your system, which measures how much contention processes face when accessing memory.

**Structure of the Output:**

- **`some`**: Refers to situations where some processes are stalled while waiting for memory.
- **`full`**: Refers to situations where all processes are stalled because memory contention is so high that no progress can be made.

Both categories provide:

1. **`avg10`**: Average memory pressure over the last 10 seconds.
2. **`avg60`**: Average memory pressure over the last 60 seconds.
3. **`avg300`**: Average memory pressure over the last 300 seconds (5 minutes).
4. **`total`**: Total time (in milliseconds) since the system boot where processes experienced this type of stall.

---

**`some` Line:**

- **`avg10=0.00 avg60=0.00 avg300=0.00`**:  
  These values indicate that, over the last 10, 60, and 300 seconds, there was no memory pressure where _some_ processes were stalled.

- **`total=77503`**:  
  Since the system boot, 77,503 milliseconds (~77.5 seconds) of cumulative time involved some processes being stalled due to memory contention.

**`full` Line:**

- **`avg10=0.00 avg60=0.00 avg300=0.00`**:  
  Over the last 10, 60, and 300 seconds, no memory pressure led to a situation where _all_ processes were stalled.

- **`total=76923`**:  
  Since the system boot, 76,923 milliseconds (~76.9 seconds) of cumulative time involved all processes being stalled due to severe memory contention.

---

# Generating Memory Pressure on Ubuntu:

```bash
# Install stress-ng
sudo apt-get install stress-ng

# Run a memory stress test
stress-ng --vm 2 --vm-bytes 75% -t 30s
```
