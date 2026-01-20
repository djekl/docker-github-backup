#!/bin/sh

echo "Project: docker-github-backup"
echo "Author:  djekl"
echo "Base:    Alpine"
echo "Target:  Generic Docker"
echo ""

# Graceful shutdown handler
shutdown() {
    echo "Received SIGTERM/SIGINT, shutting down gracefully..."
    kill $(jobs -p) 2>/dev/null  # Kill any sleeping jobs
    exit 0
}

# Trap SIGTERM and SIGINT
trap shutdown SIGTERM SIGINT

# Create necessary directories
mkdir -p /app/config
mkdir -p /app/backups

# Ensure backups dir is owned by app user
chown -R 99:100 /app/backups 2>/dev/null || echo "Note: Could not set ownership of backups"

# Copy config to working location
cp /app/config.json.example /app/config.json

# If TOKEN environment variable is set, update the config
if [ -n "$TOKEN" ]; then
    echo "Updating tokens in config..."
    if echo "$TOKEN" | grep -q ","; then
        ESCAPED_TOKENS=$(echo "$TOKEN" | sed 's/,/", "/g')
        sed -i '/"tokens"/c\  "tokens" : ["'"${ESCAPED_TOKENS}"'"],' /app/config.json
    else
        sed -i '/"tokens"/c\  "tokens" : ["'"${TOKEN}"'"],' /app/config.json || \
        sed -i '/"token"/c\  "tokens" : ["'"${TOKEN}"'"],' /app/config.json || \
        echo '  "tokens" : ["'"${TOKEN}"'"]' >> /app/config.json
    fi
fi

# Ensure directory field exists and is correct
sed -i '/"directory"/c\  "directory" : "/app/backups"' /app/config.json || \
echo '  "directory" : "/app/backups"' >> /app/config.json

echo "Starting backup process..."

# Run backup in a loop
while true; do
    echo "Running backup at $(date)..."
    python3 /app/github-backup.py /app/config.json

    # Only try to change ownership if backup directory exists
    if [ -d "/app/backups" ]; then
        chown -R 99:100 /app/backups 2>/dev/null || echo "Note: Could not change ownership of backups"
    fi

    echo "Backup completed. Waiting ${SCHEDULE:-3600}s until next run…"
    sleep "${SCHEDULE:-3600}" &
    wait $!
done
