FROM python:3.12-slim

# Install system dependencies (ffmpeg for merging, curl+unzip for deno)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install deno (required by yt-dlp for n-parameter decryption)
RUN curl -fsSL https://deno.land/install.sh | sh
ENV PATH="/root/.deno/bin:${PATH}"

# Verify deno installed
RUN deno --version

# Install yt-dlp
RUN pip install --no-cache-dir yt-dlp

WORKDIR /app

# KEY FIX: Download server.py from GitHub instead of COPYing it.
# This bypasses Docker's COPY layer cache, which was causing Render
# to serve stale server.py files even after git pushes.
# The GITHUB_SHA arg ensures this layer never caches.
ARG GITHUB_SHA=latest
RUN curl -sL "https://raw.githubusercontent.com/flourishmedia/fv-ytdlp-api/master/server.py" -o server.py

EXPOSE 8080

CMD ["python", "server.py", "8080"]
