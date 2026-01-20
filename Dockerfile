FROM alpine:3.18

# Create non-root user early for better security
RUN addgroup -g 1000 -S app && \
    adduser -u 1000 -S app -G app

# Set working directory
WORKDIR /app

# Copy only what's needed for dependency installation first (better caching)
COPY requirements.txt .
COPY github-backup.py .

# Install dependencies and clean up in one layer
RUN apk add --no-cache python3 py3-pip git && \
    pip3 install --upgrade pip && \
    pip3 install -r requirements.txt && \
    rm -f requirements.txt

# Copy remaining files
COPY config.json.example ./config.json.example
COPY backup.sh ./backup.sh

# Set proper permissions
RUN chmod +x ./backup.sh && \
    chown -R 1000:1000 /app

# Switch to non-root user
USER 1000:1000

# Create volume for backups (optional, can be mounted externally)
VOLUME ["/app/backups"]

# Define default command
CMD ["./backup.sh"]
