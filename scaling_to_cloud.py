#!/usr/bin/env python3
import psutil
import yaml
import subprocess
import time

# Load configuration from YAML file
with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

# Extract values from the config dictionary
INSTANCE_GROUP_NAME = config["instance"]["name"]
ZONE = config["instance"]["zone"]

# Thresholds for scaling up and down
CPU_SCALE_UP_THRESHOLD = 75     # If CPU usage exceeds 75%, consider scaling up
MEM_SCALE_UP_THRESHOLD = 95     # If Memory usage exceeds 95%, consider scaling up
CPU_SCALE_DOWN_THRESHOLD = 50   # If CPU usage drops below 50%, consider scaling down
MEM_SCALE_DOWN_THRESHOLD = 50   # If Memory usage drops below 50%, consider scaling down

CHECK_INTERVAL = config["instance"]["check_interval"]  # Seconds between checks

# Limits for instance group size
MAX_INSTANCES = 5
MIN_INSTANCES = 0

# Start with current instance group size.
# You may initialize this from config or assume an initial value, e.g., 0.
current_size = 0


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

        # Scale down conditions: if both metrics are well below thresholds and we have instances running
        elif (cpu_usage < CPU_SCALE_DOWN_THRESHOLD and mem_usage < MEM_SCALE_DOWN_THRESHOLD) and current_size > MIN_INSTANCES:
            current_size -= 1
            scale_instance_group(current_size)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor_resources()
