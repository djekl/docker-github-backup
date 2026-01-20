#!/bin/sh

echo "Project: github-backup"
echo "Author:  lnxd"
echo "Base:    Alpine"
echo "Target:  Generic Docker"
echo ""

# Create config directory if it doesn't exist
mkdir -p /app/config

# If config doesn't exist yet, create it from example
if [ ! -f /app/config/config.json ]; then
    echo "Creating initial config from example..."
    cp /app/config.json.example /app/config/config.json
fi

# Copy config to working location
cp /app/config/config.json /app/config.json

# If TOKEN environment variable is set, update the config
if [ -n "$TOKEN" ]; then
    echo "Updating token in config..."
    # Handle multiple tokens if TOKEN contains commas
    if echo "$TOKEN" | grep -q ","; then
        # Multiple tokens - update the tokens array
        sed -i 's|"tokens"[^,]*|&|g' /app/config.json
        sed -i '/"tokens"/c\  "tokens" : "'${TOKEN}'",\' /app/config.json
    else
        # Single token - maintain backward compatibility
        sed -i '/"token"/c\  "token" : "'${TOKEN}'",\' /app/config.json
        # Also update tokens field if it exists
        sed -i '/"tokens"/c\  "tokens" : "'${TOKEN}'",\' /app/config.json || true
    fi
fi

# Copy updated config back to persistent volume
cp /app/config.json /app/config/config.json

echo "Starting backup process..."

# Run backup in a loop
while true; do
    echo "Running backup at $(date)..."
    python3 /app/github-backup.py /app/config/config.json
    
    # Only try to change ownership if backup directory exists
    if [ -d "/app/backups" ]; then
        chown -R 1000:1000 /app/backups 2>/dev/null || echo "Note: Could not change ownership of backups"
    fi
    
    echo "Backup completed. Waiting ${SCHEDULE:-3600}s until next run..."
    sleep ${SCHEDULE:-3600}
done
