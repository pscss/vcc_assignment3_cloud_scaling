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
CPU_SCALE_UP_THRESHOLD = 75      # If local CPU > 75% trigger offloading/scale up
MEM_SCALE_UP_THRESHOLD = 90      # If local Memory > 90% trigger offloading/scale up
CPU_SCALE_DOWN_THRESHOLD = 50    # If local CPU < 50% trigger scale down
MEM_SCALE_DOWN_THRESHOLD = 50    # If local Memory < 50% trigger scale down

CHECK_INTERVAL = config["instance"]["check_interval"]  # Seconds between resource checks

# Instance group limits
MAX_INSTANCES = 5
MIN_INSTANCES = 1  # Always keep at least 1 cloud node running

# Load generation settings (used uniformly on all nodes)
NUM_LOAD_THREADS = config["instance"].get("cpu_load_threads", 1)
CPU_LOAD_CYCLE_DURATION = config["instance"].get("cpu_load_cycle_duration", 60)  # seconds

# Global variables for the controller
# current_size counts the number of cloud nodes that are running load
current_size = MIN_INSTANCES  
# active_instances holds the names of cloud nodes that are currently "sharing load"
active_instances = set()  

# --------------
# Unified Load Generator Function (Local)
# --------------
def variable_cpu_load(total_duration):
    """
    Generate CPU load that ramps up over the first half of the cycle
    and then ramps down over the second half.
    This function is used on the local machine.
    """
    cycle = 0.1  # mini-cycle duration in seconds
    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        fraction = (elapsed % total_duration) / total_duration
        # Ramp up in first half, ramp down in second half:
        intensity = fraction / 0.5 if fraction < 0.5 else (1 - fraction) / 0.5
        busy_time = cycle * intensity
        sleep_time = cycle - busy_time
        t_start = time.time()
        # Busy loop to burn CPU cycles:
        while time.time() - t_start < busy_time:
            _ = sum(i * i for i in range(1000))
        time.sleep(sleep_time)

def start_local_load(num_threads, cycle_duration):
    """
    Start local load generator threads.
    """
    for _ in range(num_threads):
        t = threading.Thread(target=variable_cpu_load, args=(cycle_duration,), daemon=True)
        t.start()
    print(f"Started {num_threads} local load thread(s) with a {cycle_duration}-second cycle.")

# --------------
# Remote Load Functions (for Cloud Nodes)
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
    Remotely start a load generator on the cloud instance.
    We use a one-liner that burns CPU cycles directly on the remote node.
    """
    remote_command = (
        "nohup python3 -c \"import time, math; "
        "while True: [math.sqrt(i) for i in range(10000)]; time.sleep(0.1)\" "
        "> /dev/null 2>&1 &"
    )
    cmd = [
        "gcloud", "compute", "ssh", instance_name,
        f"--zone={ZONE}",
        "--command", remote_command
    ]
    try:
        subprocess.run(cmd, check=True)
        print(f"Started remote load on instance: {instance_name}")
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

# --------------
# Monitoring & Scaling Controller
# --------------
def monitor_resources():
    """
    Sequence:
      1. Run local load.
      2. When local CPU > 75% or Memory > 90%, check if a cloud node is available.
         - If a cloud node is available but not yet running load, remotely start load on it.
         - Otherwise, if no cloud node is available, scale up the instance group (up to MAX_INSTANCES).
      3. As load further increases, keep scaling up until there are 5 cloud nodes sharing the load.
      4. Once at 5 cloud nodes, if load drops below 50% CPU and 50% memory,
         scale down one cloud node at a time (ensuring at least one remains) until local load is below threshold.
      5. Continually print the total (local) CPU and Memory usage.
    """
    global current_size, active_instances

    while True:
        cpu_usage = psutil.cpu_percent(interval=1)
        mem_usage = psutil.virtual_memory().percent
        print(f"Local CPU: {cpu_usage}% | Memory: {mem_usage}% | Cloud nodes: {current_size}")
        
        # --- Scaling Up or Offloading Load ---
        if (cpu_usage > CPU_SCALE_UP_THRESHOLD or mem_usage > MEM_SCALE_UP_THRESHOLD):
            # Check if there is any available cloud node (from instance group) that is not yet sharing load.
            available_nodes = get_instance_names() - active_instances
            if available_nodes:
                # Offload: Pick one available cloud node to start remote load.
                node = list(available_nodes)[0]
                print(f"Offloading load to available cloud node: {node}")
                if wait_for_instance(node):
                    start_remote_load(node)
                    active_instances.add(node)
                    # Update current_size if needed.
                    current_size = max(current_size, len(active_instances))
                else:
                    print(f"Cloud node {node} not ready for load offloading.")
            else:
                # No available node found – scale up if not at maximum.
                if current_size < MAX_INSTANCES:
                    before_nodes = get_instance_names()
                    desired_size = current_size + 1
                    scale_instance_group(desired_size)
                    
                    new_node = None
                    timeout = 300  # seconds to wait for new node detection
                    start_wait = time.time()
                    while time.time() - start_wait < timeout:
                        after_nodes = get_instance_names()
                        diff = after_nodes - before_nodes
                        if diff:
                            new_node = list(diff)[0]
                            break
                        time.sleep(5)
                    
                    if new_node:
                        print(f"New cloud node detected: {new_node}. Waiting for it to be ready...")
                        if wait_for_instance(new_node):
                            start_remote_load(new_node)
                            active_instances.add(new_node)
                            current_size = desired_size
                        else:
                            print(f"Cloud node {new_node} did not become RUNNING. Reverting scale-up.")
                            scale_instance_group(current_size)
                    else:
                        print("No new cloud node detected after scaling up. Reverting scale-up.")
                        scale_instance_group(current_size)
                else:
                    print("Maximum cloud nodes reached. Load offloading is already in effect.")

        # --- Scaling Down ---
        elif (cpu_usage < CPU_SCALE_DOWN_THRESHOLD and mem_usage < MEM_SCALE_DOWN_THRESHOLD):
            if current_size > MIN_INSTANCES:
                if active_instances:
                    # Remove one cloud node from sharing load.
                    node_to_remove = list(active_instances)[-1]
                    desired_size = current_size - 1
                    scale_instance_group(desired_size)
                    print(f"Scaling down: Removing cloud node {node_to_remove}.")
                    active_instances.remove(node_to_remove)
                    current_size = desired_size
                else:
                    print("No active cloud node to remove, though scale down conditions met.")
            else:
                print("At minimum cloud node count; cannot scale down further.")

        # Sleep for the check interval before next monitoring iteration.
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
        # For local or cloud node load generation.
        start_local_load(NUM_LOAD_THREADS, CPU_LOAD_CYCLE_DURATION)
        while True:
            time.sleep(1)
    else:
        # Controller mode: start local load and manage cloud node scaling/offloading.
        print("Starting unified load generator on local node and initiating cluster monitoring...")
        start_local_load(NUM_LOAD_THREADS, CPU_LOAD_CYCLE_DURATION)
        monitor_resources()
