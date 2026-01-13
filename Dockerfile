FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Setup entrypoint script
RUN chmod +x entrypoint.sh

# Create necessary directories
RUN mkdir -p downloads cookies logs

# Expose port
EXPOSE 8000

# Use entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command (passed to entrypoint as $@)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
