FROM alpine:3.18
LABEL org.opencontainers.image.description "Backup GitHub Repos Locally using GitHub Access Tokens"

# Create non-root user matching Unraid's default UID/GID
RUN adduser -D -u 99 -G users app

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
    chown -R 99:100 /app

# Switch to non-root user
USER 99:100

# Define default command
CMD ["./backup.sh"]
