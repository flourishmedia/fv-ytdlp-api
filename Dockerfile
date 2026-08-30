FROM python:3.12-slim

# Install system dependencies (ffmpeg for merging, curl+unzip for deno)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install deno (required by yt-dlp for n-parameter decryption)
# Must install AFTER curl and unzip are available
RUN curl -fsSL https://deno.land/install.sh | sh
ENV PATH="/root/.deno/bin:${PATH}"

# Verify deno installed
RUN deno --version

# Install yt-dlp
RUN pip install --no-cache-dir yt-dlp

WORKDIR /app
COPY server.py .

EXPOSE 8080

CMD ["python", "server.py", "8080"]
# Build Sun, Aug 30, 2026  9:49:57 PM
