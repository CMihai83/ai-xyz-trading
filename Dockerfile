FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire ai_xyz system
COPY . .

# Create necessary directories
RUN mkdir -p logs data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose ports if needed (for API)
EXPOSE 8000 8765

# Default command to run the main trading system
CMD ["python3", "aixyz_continuous_profit_system.py"]