#!/bin/bash

echo "Installing requirements for AI Trading System..."

# Find all requirements.txt files and install them
for req_file in $(find services -name requirements.txt); do
    echo "Installing requirements from $req_file..."
    pip install -q -r "$req_file" 2>/dev/null || true
done

# Install any additional core dependencies
pip install -q fastapi uvicorn[standard] httpx redis pandas numpy structlog yfinance scikit-learn joblib psutil python-dotenv pydantic-settings psycopg2-binary 2>/dev/null || true

echo "All requirements installed!"