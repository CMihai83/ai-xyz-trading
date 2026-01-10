FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libpq-dev \
    netcat-openbsd \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create necessary directories
RUN mkdir -p /var/log/florin_trading \
    && mkdir -p /app/data \
    && mkdir -p /app/logs \
    && mkdir -p /app/pids

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV LOG_DIR=/var/log/florin_trading
ENV DATA_DIR=/app/data
ENV REDIS_DB=2

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
echo "=========================================="\n\
echo "Starting Florin Trading System"\n\
echo "=========================================="\n\
echo "Redis DB: ${REDIS_DB}"\n\
echo "Log Directory: ${LOG_DIR}"\n\
echo "Data Directory: ${DATA_DIR}"\n\
echo "=========================================="\n\
\n\
# Wait for Redis to be ready\n\
echo "Waiting for Redis..."\n\
REDIS_HOST=${REDIS_HOST:-redis}\n\
REDIS_PORT=${REDIS_PORT:-6379}\n\
\n\
while ! nc -z $REDIS_HOST $REDIS_PORT; do\n\
  echo "Redis is unavailable - sleeping"\n\
  sleep 2\n\
done\n\
echo "Redis is ready!"\n\
\n\
# Wait for PostgreSQL if configured\n\
if [ -n "${POSTGRES_HOST}" ]; then\n\
  echo "Waiting for PostgreSQL..."\n\
  while ! nc -z ${POSTGRES_HOST} ${POSTGRES_PORT:-5432}; do\n\
    echo "PostgreSQL is unavailable - sleeping"\n\
    sleep 2\n\
  done\n\
  echo "PostgreSQL is ready!"\n\
fi\n\
\n\
# Start the trading system\n\
echo "Starting trading system..."\n\
exec python3 aixyz_continuous_profit_system.py\n\
' > /app/start.sh && chmod +x /app/start.sh

# Expose ports (for web dashboard if needed)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python3 -c "import sys; sys.exit(0)" || exit 1

# Run the application
CMD ["/app/start.sh"]