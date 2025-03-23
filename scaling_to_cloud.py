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
# MACHINE_TYPE = config["instance"]["machine_type"]
# IMAGE_FAMILY = config["instance"]["image_family"]
# IMAGE_PROJECT = config["instance"]["image_project"]
THRESHOLD = config["instance"]["threshold"]  # Percentage for CPU and Memory usage
CHECK_INTERVAL = config["instance"]["check_interval"]  # Seconds between checks


import subprocess

def scale_instance_group(new_size):
    """
    Resize a managed instance group to the desired number of instances.
    
    Parameters:
        new_size (int): The new desired number of instances in the group.
    """
    print(f"Threshold exceeded. Resizing instance group to {new_size} instances...")
    command = [
        "gcloud",
        "compute",
        "instance-groups",
        "managed",
        "resize",
        INSTANCE_GROUP_NAME,  # Ensure this variable is defined with your instance group name
        f"--zone={ZONE}",     # Ensure ZONE is set to your instance group's zone
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
    Monitor CPU and Memory usage. If usage exceeds the threshold, trigger auto-scaling.
    """
    while True:
        cpu_usage = psutil.cpu_percent(interval=1)
        mem_usage = psutil.virtual_memory().percent
        print(f"CPU Usage: {cpu_usage}% | Memory Usage: {mem_usage}%")

        if cpu_usage > THRESHOLD or mem_usage > THRESHOLD:
            scale_instance_group()
            # Optional: Break or pause the monitor if only one instance should be launched
            # break

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    monitor_resources()
