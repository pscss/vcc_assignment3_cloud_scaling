#!/bin/bash

# Constants and configuration
ZONE="us-central1-a"
INSTANCE_GROUP_NAME="my-hybrid-mig"
INSTANCE_TEMPLATE="instance-template-20250323-125636"
MAX_REPLICAS=5
TARGET_CPU=0.6
COOLDOWN=90
# Replace this with your local VM's IP address (without CIDR notation)
LOCAL_VM_IP="<YOUR_LOCAL_VM_IP>"

function create_mig() {
  echo "Creating Managed Instance Group: $INSTANCE_GROUP_NAME in zone $ZONE..."
  gcloud compute instance-groups managed create $INSTANCE_GROUP_NAME \
    --base-instance-name cloud-node \
    --template=$INSTANCE_TEMPLATE \
    --size=0 \
    --zone=$ZONE
  if [ $? -ne 0 ]; then
    echo "Error creating Managed Instance Group."
    exit 1
  fi

  echo "Configuring autoscaling for $INSTANCE_GROUP_NAME..."
  gcloud compute instance-groups managed set-autoscaling $INSTANCE_GROUP_NAME \
    --max-num-replicas=$MAX_REPLICAS \
    --min-num-replicas=0 \
    --target-cpu-utilization=$TARGET_CPU \
    --cool-down-period=$COOLDOWN \
    --zone=$ZONE
  if [ $? -ne 0 ]; then
    echo "Error configuring autoscaling."
    exit 1
  fi

  echo "Creating firewall rule to allow incoming TCP traffic on port 80..."
  gcloud compute firewall-rules create allow-hybrid-cluster \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:80 \
    --source-ranges=${LOCAL_VM_IP}/32 2>/dev/null || echo "Firewall rule may already exist."
  
  echo "Managed Instance Group and autoscaling setup completed."
}

function delete_mig() {
  echo "Deleting Managed Instance Group: $INSTANCE_GROUP_NAME from zone $ZONE..."
  gcloud compute instance-groups managed delete $INSTANCE_GROUP_NAME --zone=$ZONE --quiet
  if [ $? -eq 0 ]; then
    echo "Managed Instance Group deleted successfully."
  else
    echo "Error deleting Managed Instance Group."
  fi
}

# Main script logic
if [ "$1" == "close" ]; then
  delete_mig
else
  create_mig
fi
