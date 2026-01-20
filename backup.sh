#!/bin/sh

echo "Project: docker-github-backup"
echo "Author:  djekl"
echo "Base:    Alpine"
echo "Target:  Generic Docker"
echo ""

# Create config directory if it doesn't exist
mkdir -p /app/config
mkdir -p /app/backups

# If config doesn't exist yet, create it from example
if [ ! -f /app/config/config.json ]; then
    echo "Creating initial config from example..."
    cp /app/config.json.example /app/config/config.json
fi

# Copy config to working location
cp /app/config/config.json /app/config.json

# If TOKEN environment variable is set, update the config
if [ -n "$TOKEN" ]; then
    echo "Updating tokens in config..."
    # Handle multiple tokens if TOKEN contains commas, otherwise single token
    if echo "$TOKEN" | grep -q ","; then
        # Multiple tokens - create proper JSON array
        ESCAPED_TOKENS=$(echo "$TOKEN" | sed 's/,/", "/g')
        sed -i '/"tokens"/c\  "tokens" : ["'"${ESCAPED_TOKENS}"'"],\' /app/config.json
    else
        # Single token - create tokens array with one element
        sed -i '/"tokens"/c\  "tokens" : ["'"${TOKEN}"'"],\' /app/config.json || \
        sed -i '/"token"/c\  "tokens" : ["'"${TOKEN}"'"],\' /app/config.json || \
        echo '  "tokens" : ["'"${TOKEN}"'"]' >> /app/config.json
    fi
fi

# Ensure directory field exists and is correct
sed -i '/"directory"/c\  "directory" : "/app/backups"' /app/config.json || \
echo '  "directory" : "/app/backups"' >> /app/config.json

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
