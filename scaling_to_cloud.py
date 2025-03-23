#!/usr/bin/env python3
import psutil
import yaml
import subprocess
import time
import threading

# Load configuration from YAML file
with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

# Extract values from the config dictionary
INSTANCE_GROUP_NAME = config["instance"]["name"]
ZONE = config["instance"]["zone"]

# Thresholds for scaling up and down
CPU_SCALE_UP_THRESHOLD = 75     # Scale up if CPU usage exceeds 75%
MEM_SCALE_UP_THRESHOLD = 95     # Scale up if Memory usage exceeds 95%
CPU_SCALE_DOWN_THRESHOLD = 50   # Scale down if CPU usage drops below 50%
MEM_SCALE_DOWN_THRESHOLD = 50   # Scale down if Memory usage drops below 50%

CHECK_INTERVAL = config["instance"]["check_interval"]  # Seconds between resource checks

# Limits for instance group size
MAX_INSTANCES = 5
MIN_INSTANCES = 0

# Starting instance group size
current_size = 0

# CPU load generation configuration
NUM_LOAD_THREADS = config["instance"].get("cpu_load_threads", 1)  # Default to 1 thread
# Total duration (in seconds) for one complete load cycle (ramp up then ramp down)
CPU_LOAD_CYCLE_DURATION = config["instance"].get("cpu_load_cycle_duration", 60)  # Default 60 seconds


def scale_instance_group(new_size):
    """
    Resize a managed instance group to the desired number of instances.
    
    Parameters:
        new_size (int): The new desired number of instances in the group.
    """
    print(f"Resizing instance group '{INSTANCE_GROUP_NAME}' to {new_size} instances in zone {ZONE}...")
    command = [
        "gcloud",
        "compute",
        "instance-groups",
        "managed",
        "resize",
        INSTANCE_GROUP_NAME,
        f"--zone={ZONE}",
        f"--size={new_size}",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print("Instance group resize output:")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("Error resizing instance group:")
        print(e.stderr)


def monitor_resources():
    """
    Monitor CPU and Memory usage, scaling up or down the managed instance group dynamically.
    - If CPU usage > 75% or Memory usage > 95%, increase the instance count (max 5).
    - If CPU usage < 50% and Memory usage < 50%, decrease the instance count (min 0).
    """
    global current_size

    while True:
        cpu_usage = psutil.cpu_percent(interval=1)
        mem_usage = psutil.virtual_memory().percent
        print(f"CPU Usage: {cpu_usage}% | Memory Usage: {mem_usage}% | Current instances: {current_size}")

        # Scale up conditions: if any usage exceeds threshold and we haven't reached the max
        if (cpu_usage > CPU_SCALE_UP_THRESHOLD or mem_usage > MEM_SCALE_UP_THRESHOLD) and current_size < MAX_INSTANCES:
            current_size += 1
            scale_instance_group(current_size)

        # Scale down conditions: if both metrics are below thresholds and we have instances running
        elif (cpu_usage < CPU_SCALE_DOWN_THRESHOLD and mem_usage < MEM_SCALE_DOWN_THRESHOLD) and current_size > MIN_INSTANCES:
            current_size -= 1
            scale_instance_group(current_size)

        time.sleep(CHECK_INTERVAL)


def variable_cpu_load(total_duration):
    """
    Generate CPU load that ramps up over the first half of the cycle and
    then ramps down over the second half. This cycle repeats indefinitely.
    
    Parameters:
        total_duration (float): Total duration (in seconds) of one complete cycle.
    """
    cycle = 0.1  # Duration of each mini-cycle in seconds
    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        fraction = elapsed / total_duration

        if fraction >= 1.0:
            # Reset cycle when complete
            start_time = time.time()
            fraction = 0.0

        # Calculate intensity: ramp up for the first half, then ramp down.
        if fraction < 0.5:
            intensity = fraction / 0.5  # 0.0 to 1.0
        else:
            intensity = (1 - fraction) / 0.5  # 1.0 to 0.0

        # Determine busy and sleep times based on intensity.
        busy_time = cycle * intensity
        sleep_time = cycle - busy_time

        # Busy work: simple loop to burn CPU cycles.
        t_start = time.time()
        while time.time() - t_start < busy_time:
            pass

        time.sleep(sleep_time)


def start_cpu_load(num_threads, cycle_duration):
    """
    Start a specified number of threads to generate variable CPU load.
    
    Parameters:
        num_threads (int): Number of threads to spawn.
        cycle_duration (float): Duration for one full ramp-up and ramp-down cycle.
    """
    for i in range(num_threads):
        t = threading.Thread(target=variable_cpu_load, args=(cycle_duration,), daemon=True)
        t.start()
    print(f"Started {num_threads} CPU load thread(s) with a {cycle_duration}-second cycle.")


if __name__ == "__main__":
    # Start generating artificial variable CPU load
    start_cpu_load(NUM_LOAD_THREADS, CPU_LOAD_CYCLE_DURATION)
    # Begin monitoring resources and scaling accordingly
    monitor_resources()
