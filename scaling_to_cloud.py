#!/usr/bin/env python3
import argparse
import psutil
import yaml
import subprocess
import time
import threading

# --------------
# Load Configuration
# --------------
with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

INSTANCE_GROUP_NAME = config["instance"]["name"]
ZONE = config["instance"]["zone"]

# Thresholds for scaling decisions (for the overall cluster)
CPU_SCALE_UP_THRESHOLD = 75      # Scale up if CPU usage exceeds 75%
MEM_SCALE_UP_THRESHOLD = 95      # Scale up if Memory usage exceeds 95%
CPU_SCALE_DOWN_THRESHOLD = 50    # Scale down if CPU usage drops below 50%
MEM_SCALE_DOWN_THRESHOLD = 50    # Scale down if Memory usage drops below 50%

CHECK_INTERVAL = config["instance"]["check_interval"]  # Seconds between resource checks

# Instance group limits
MAX_INSTANCES = 5
MIN_INSTANCES = 0

# Load generation settings (used uniformly on all nodes)
NUM_LOAD_THREADS = config["instance"].get("cpu_load_threads", 1)
CPU_LOAD_CYCLE_DURATION = config["instance"].get("cpu_load_cycle_duration", 60)  # seconds

# Global variables for the controller
current_size = 0  # current number of cloud instances in the managed group
active_instances = set()  # names of cloud instances running our load generator

# --------------
# Unified Load Generator Function
# --------------
def variable_cpu_load(total_duration):
    """
    Generate CPU load that ramps up over the first half of the cycle
    and then ramps down over the second half.
    This function is used on both local and cloud VMs.
    """
    cycle = 0.1  # mini-cycle duration in seconds
    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        fraction = (elapsed % total_duration) / total_duration

        # Ramp up in the first half, then ramp down
        if fraction < 0.5:
            intensity = fraction / 0.5  # increases from 0 to 1
        else:
            intensity = (1 - fraction) / 0.5  # decreases from 1 to 0

        busy_time = cycle * intensity
        sleep_time = cycle - busy_time

        t_start = time.time()
        # Busy loop to burn CPU cycles
        while time.time() - t_start < busy_time:
            _ = sum(i * i for i in range(1000))
        time.sleep(sleep_time)

def start_local_load(num_threads, cycle_duration):
    """
    Start load generator threads locally.
    """
    for _ in range(num_threads):
        t = threading.Thread(target=variable_cpu_load, args=(cycle_duration,), daemon=True)
        t.start()
    print(f"Started {num_threads} local CPU load thread(s) with a {cycle_duration}-second cycle.")

# --------------
# Remote Load Functions (for cloud VMs)
# --------------
def wait_for_instance(instance_name, timeout=300):
    """
    Wait until the given instance's status is RUNNING.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        cmd = [
            "gcloud", "compute", "instances", "describe", instance_name,
            f"--zone={ZONE}",
            "--format=value(status)"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        status = result.stdout.strip()
        if status == "RUNNING":
            print(f"Instance {instance_name} is RUNNING.")
            return True
        time.sleep(5)
    return False

def start_remote_load(instance_name):
    """
    Remotely start the unified load generator on the cloud instance.
    Assumes that the remote instance has this script (or an equivalent load generator)
    at a specified path (adjust REMOTE_SCRIPT_PATH accordingly).
    """
    REMOTE_SCRIPT_PATH = "/home/your_username/load_generator.py"  # adjust as needed
    remote_command = (
        f"nohup python3 {REMOTE_SCRIPT_PATH} --run-load > /dev/null 2>&1 &"
    )
    cmd = [
        "gcloud", "compute", "ssh", instance_name,
        f"--zone={ZONE}",
        "--command", remote_command
    ]
    try:
        subprocess.run(cmd, check=True)
        print(f"Started unified load generator on remote instance: {instance_name}")
    except subprocess.CalledProcessError as e:
        print(f"Error starting remote load on {instance_name}: {e}")

def get_instance_names():
    """
    Return a set of instance names currently in the managed instance group.
    """
    cmd = [
        "gcloud", "compute", "instance-groups", "managed", "list-instances",
        INSTANCE_GROUP_NAME,
        f"--zone={ZONE}",
        "--format=value(instance)"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    instances = set(result.stdout.strip().splitlines())
    return instances

# --------------
# Scaling and Monitoring Logic
# --------------
def scale_instance_group(new_size):
    """
    Resize the managed instance group to new_size.
    """
    print(f"Resizing instance group '{INSTANCE_GROUP_NAME}' to {new_size} instances in zone {ZONE}...")
    cmd = [
        "gcloud", "compute", "instance-groups", "managed", "resize",
        INSTANCE_GROUP_NAME,
        f"--zone={ZONE}",
        f"--size={new_size}"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("Resize output:")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("Error resizing instance group:")
        print(e.stderr)

def monitor_resources():
    """
    Monitor local CPU and Memory usage and manage scaling of the cluster.
    
    - If local CPU > 75% or Memory > 95% and group size < MAX_INSTANCES,
      scale up. After scaling up, wait for the new instance to be RUNNING and
      remotely start the unified load generator.
    
    - If local CPU < 50% and Memory < 50% and group size > MIN_INSTANCES,
      scale down one instance (which will eventually stop running the load).
    """
    global current_size, active_instances

    while True:
        cpu_usage = psutil.cpu_percent(interval=1)
        mem_usage = psutil.virtual_memory().percent
        print(f"Local CPU: {cpu_usage}% | Memory: {mem_usage}% | Cloud instances: {current_size}")

        # --- Scaling Up ---
        if (cpu_usage > CPU_SCALE_UP_THRESHOLD or mem_usage > MEM_SCALE_UP_THRESHOLD) and current_size < MAX_INSTANCES:
            before_instances = get_instance_names()
            desired_size = current_size + 1
            scale_instance_group(desired_size)
            
            new_instance = None
            timeout = 300  # seconds to wait for new instance detection
            start_wait = time.time()
            while time.time() - start_wait < timeout:
                after_instances = get_instance_names()
                diff = after_instances - before_instances
                if diff:
                    new_instance = list(diff)[0]
                    break
                time.sleep(5)
            
            if new_instance:
                print(f"New instance detected: {new_instance}. Waiting for it to be ready...")
                if wait_for_instance(new_instance):
                    start_remote_load(new_instance)
                    active_instances.add(new_instance)
                    current_size = desired_size  # update only if new instance came online
                else:
                    print(f"Instance {new_instance} did not become RUNNING in time.")
            else:
                print("No new instance detected after scaling up. Reverting desired size.")
        
        # --- Scaling Down ---
        elif (cpu_usage < CPU_SCALE_DOWN_THRESHOLD and mem_usage < MEM_SCALE_DOWN_THRESHOLD) and current_size > MIN_INSTANCES:
            if active_instances:
                # Remove one instance from the cloud cluster
                instance_to_remove = list(active_instances)[-1]
                current_size -= 1
                scale_instance_group(current_size)
                print(f"Scaling down: Instance {instance_to_remove} scheduled for removal.")
                active_instances.remove(instance_to_remove)
            else:
                print("No active remote load instance found to scale down.")

        time.sleep(CHECK_INTERVAL)

# --------------
# Main Execution Block with Argument Parsing
# --------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified Load Generator and Cluster Scaling Controller")
    parser.add_argument("--run-load", action="store_true",
                        help="Run the unified load generator function (for local or remote node).")
    args = parser.parse_args()

    if args.run_load:
        # This branch runs on any node (local or cloud) that should generate load.
        start_local_load(NUM_LOAD_THREADS, CPU_LOAD_CYCLE_DURATION)
        # Keep the load generator running indefinitely.
        while True:
            time.sleep(1)
    else:
        # Controller mode: start local load and manage scaling across the cluster.
        print("Starting unified load generator on local node and initiating cluster monitoring...")
        start_local_load(NUM_LOAD_THREADS, CPU_LOAD_CYCLE_DURATION)
        monitor_resources()
