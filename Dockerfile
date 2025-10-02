# --- Dockerfile for FTM Alpha Forwarder Bot ---

# Use official Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements file (you can create one with necessary packages)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# Set environment variables (you can override them in Render dashboard)

# Expose the port for Render
EXPOSE 8000

# Run the bot
CMD ["python", "main.py"]
