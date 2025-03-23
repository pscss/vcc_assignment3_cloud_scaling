import time
import psutil
import logging
import configparser

from googleapiclient import discovery

# Load configuration from config.ini
config = configparser.ConfigParser()
config.read('config.ini')

# Google Cloud configuration
INSTANCE_GROUP_NAME = config.get('GoogleCloud', 'instance_group_name')
ZONE = config.get('GoogleCloud', 'zone')
PROJECT = config.get('GoogleCloud', 'project')

# Thresholds for scaling
CPU_THRESHOLD_UP = config.getfloat('Thresholds', 'cpu_threshold_up')
MEM_THRESHOLD_UP = config.getfloat('Thresholds', 'mem_threshold_up')
CPU_THRESHOLD_DOWN = config.getfloat('Thresholds', 'cpu_threshold_down')
MEM_THRESHOLD_DOWN = config.getfloat('Thresholds', 'mem_threshold_down')

# Scaling limits
MAX_CLOUD_NODES = config.getint('Scaling', 'max_cloud_nodes')
MIN_CLOUD_NODES = config.getint('Scaling', 'min_cloud_nodes')

def get_local_load():
    """
    Returns the local machine's CPU and memory usage percentages.
    """
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory().percent
    return cpu, mem

def get_cloud_instances(compute, project, zone, instance_group):
    """
    Retrieves the list of running instances in the cloud instance group.
    Note: This example uses the instanceGroups() API. For a managed instance group,
    consider using instanceGroupManagers().listManagedInstances() instead.
    """
    try:
        request = compute.instanceGroups().listInstances(
            project=project,
            zone=zone,
            instanceGroup=instance_group,
            body={"instanceState": "RUNNING"}
        )
        response = request.execute()
        instances = response.get("items", [])
        return instances
    except Exception as e:
        logging.error(f"Error fetching cloud instances: {e}")
        return []

def add_cloud_instance(compute, project, zone, instance_group):
    """
    Adds a new instance to the cloud instance group.
    For managed instance groups, you would typically call a resize method.
    """
    try:
        logging.info("Scaling out: Adding a new cloud instance.")
        # Example for a managed instance group:
        # current_size = get_current_instance_count(compute, project, zone, instance_group)
        # new_size = current_size + 1
        # request = compute.instanceGroupManagers().resize(
        #     project=project,
        #     zone=zone,
        #     instanceGroupManager=instance_group,
        #     size=new_size
        # )
        # response = request.execute()
        time.sleep(2)  # Simulate delay for the instance to be added
    except Exception as e:
        logging.error(f"Error adding cloud instance: {e}")

def remove_cloud_instance(compute, project, zone, instance_group):
    """
    Removes one instance from the cloud instance group.
    For a managed instance group, you would typically reduce the group’s size.
    """
    try:
        logging.info("Scaling in: Removing one cloud instance.")
        # Example for a managed instance group:
        # current_size = get_current_instance_count(compute, project, zone, instance_group)
        # new_size = current_size - 1
        # request = compute.instanceGroupManagers().resize(
        #     project=project,
        #     zone=zone,
        #     instanceGroupManager=instance_group,
        #     size=new_size
        # )
        # response = request.execute()
        time.sleep(2)  # Simulate delay for the instance removal
    except Exception as e:
        logging.error(f"Error removing cloud instance: {e}")

def monitor_and_scale():
    """
    Monitors the local load and adjusts cloud node count based on thresholds.
    It also simulates sharing load between the local machine and cloud nodes.
    """
    # Initialize the Google Cloud compute API client.
    # Since the Cloud SDK is installed and the project is set, we can build without manual credentials.
    compute = discovery.build('compute', 'v1')
    
    while True:
        # Get local system metrics
        local_cpu, local_mem = get_local_load()
        logging.info(f"Local load - CPU: {local_cpu:.1f}%, Memory: {local_mem:.1f}%")
        
        # Get current cloud instance count
        cloud_instances = get_cloud_instances(compute, PROJECT, ZONE, INSTANCE_GROUP_NAME)
        cloud_instance_count = len(cloud_instances)
        logging.info(f"Current cloud instance count: {cloud_instance_count}")
        
        # Scale-out conditions: If high load on local system
        if local_cpu > CPU_THRESHOLD_UP or local_mem > MEM_THRESHOLD_UP:
            logging.info("High local load detected.")
            if cloud_instance_count >= MIN_CLOUD_NODES:
                logging.info("Cloud nodes available: sharing load between local and cloud nodes.")
            # Add an instance if maximum not reached
            if cloud_instance_count < MAX_CLOUD_NODES:
                logging.info("Further high load: triggering scale-out procedure.")
                add_cloud_instance(compute, PROJECT, ZONE, INSTANCE_GROUP_NAME)
            else:
                logging.info("Maximum cloud nodes reached; cannot add more instances.")
                
        # Scale-in conditions: If low load on local system
        elif local_cpu < CPU_THRESHOLD_DOWN and local_mem < MEM_THRESHOLD_DOWN:
            logging.info("Low load detected.")
            if cloud_instance_count > MIN_CLOUD_NODES:
                logging.info("Scale-in: removing one cloud node to optimize resources.")
                remove_cloud_instance(compute, PROJECT, ZONE, INSTANCE_GROUP_NAME)
            else:
                logging.info("Only one cloud node running; no scale-in action taken.")
        else:
            logging.info("Load within acceptable thresholds. No scaling actions taken.")
        
        # Monitoring the total cluster load (local + cloud nodes).
        # In a real scenario, you might also query each cloud node for its individual metrics.
        logging.info("Monitoring total cluster load (local + cloud nodes).")
        
        # Wait before next monitoring cycle
        time.sleep(10)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    monitor_and_scale()
