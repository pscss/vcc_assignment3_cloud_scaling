#!/usr/bin/env python3
import psutil
import subprocess
import time

# Configuration parameters
THRESHOLD = 75  # Percentage for CPU and Memory usage
CHECK_INTERVAL = 5  # Seconds between checks
INSTANCE_NAME = "auto-scaled-instance"
ZONE = "us-central1-a"
MACHINE_TYPE = "e2-medium"
IMAGE_FAMILY = "debian-11"
IMAGE_PROJECT = "debian-cloud"


def scale_to_public_cloud():
    """
    Trigger a Google Cloud VM creation using the gcloud CLI.
    """
    print("Threshold exceeded. Launching new public cloud instance...")
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
