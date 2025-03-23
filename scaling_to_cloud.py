#!/usr/bin/env python3
import psutil
import yaml
import subprocess
import time


# Load configuration from YAML file
with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

# Extract values from the config dictionary
INSTANCE_NAME = config["instance"]["name"]
ZONE = config["instance"]["zone"]
MACHINE_TYPE = config["instance"]["machine_type"]
IMAGE_FAMILY = config["instance"]["image_family"]
IMAGE_PROJECT = config["instance"]["image_project"]
THRESHOLD = config["instance"]["threshold"]  # Percentage for CPU and Memory usage
CHECK_INTERVAL = config["instance"]["check_interval"]  # Seconds between checks


def scale_to_public_cloud():
    """
    Trigger a Google Cloud VM creation using the gcloud CLI.
    """
    print("Threshold exceeded. Launching new public cloud instance...")
    # Build the command list using the config values
    command = [
        "gcloud",
        "compute",
        "instances",
        "create",
        INSTANCE_NAME,
        f"--zone={ZONE}",
        f"--machine-type={MACHINE_TYPE}",
        f"--image-family={IMAGE_FAMILY}",
        f"--image-project={IMAGE_PROJECT}",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print("Instance creation output:")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("Error creating instance:")
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
            scale_to_public_cloud()
            # Optional: Break or pause the monitor if only one instance should be launched
            # break

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    monitor_resources()
