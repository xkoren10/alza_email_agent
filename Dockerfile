# Use official lightweight Python 3.12 image
FROM python:3.12-slim

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory inside container
WORKDIR /app

# Install essential system dependencies (if any wheels require compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and prebuilt vector indices
COPY . /app/

# Expose any ports if needed (optional for background polling worker)
# EXPOSE 8080

# Run the main polling script (you can pass --no-reply as a default or override it via docker run)
ENTRYPOINT ["python", "main.py"]