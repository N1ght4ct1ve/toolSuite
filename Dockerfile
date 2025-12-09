FROM python:3.11-slim-bookworm

# Install system dependencies
# libsndfile1 is required for soundfile
# espeak-ng is required for phonemizer (used by kokoro/TTS)
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    espeak-ng \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install spaCy model required by Kokoro
RUN python -m spacy download en_core_web_sm

# Copy the application code
COPY . .

# Create directories for uploads and audio
RUN mkdir -p uploads audio

# Expose the port
EXPOSE 5000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "app.py"]
