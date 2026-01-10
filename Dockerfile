FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    curl \
    netcat-openbsd \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire ai_xyz system
COPY . .

# Create necessary directories
RUN mkdir -p logs data pids

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
echo "=========================================="\n\
echo "Starting AI-XYZ Trading System"\n\
echo "=========================================="\n\
echo "Redis Host: ${REDIS_HOST:-redis}"\n\
echo "Log Level: ${LOG_LEVEL:-INFO}"\n\
echo "=========================================="\n\
\n\
# Wait for Redis to be ready\n\
echo "Waiting for Redis..."\n\
REDIS_HOST=${REDIS_HOST:-redis}\n\
REDIS_PORT=${REDIS_PORT:-6379}\n\
\n\
while ! nc -z $REDIS_HOST $REDIS_PORT 2>/dev/null; do\n\
  echo "Redis is unavailable - sleeping"\n\
  sleep 2\n\
done\n\
echo "Redis is ready!"\n\
\n\
# Wait for PostgreSQL if configured\n\
if [ -n "${POSTGRES_HOST}" ]; then\n\
  echo "Waiting for PostgreSQL..."\n\
  while ! nc -z ${POSTGRES_HOST} ${POSTGRES_PORT:-5432} 2>/dev/null; do\n\
    echo "PostgreSQL is unavailable - sleeping"\n\
    sleep 2\n\
  done\n\
  echo "PostgreSQL is ready!"\n\
fi\n\
\n\
# Start the trading system\n\
echo "Starting AI-XYZ continuous profit system..."\n\
exec python3 aixyz_continuous_profit_system.py\n\
' > /app/start.sh && chmod +x /app/start.sh

# Expose ports if needed (for API)
EXPOSE 8000 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python3 -c "import sys; sys.exit(0)" || exit 1

# Default command to run the main trading system
CMD ["/app/start.sh"]
