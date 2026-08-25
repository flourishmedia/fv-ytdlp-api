FROM python:3.12-slim

# Install ffmpeg (REQUIRED by yt-dlp for merging video+audio streams)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install deno (REQUIRED by yt-dlp for n-parameter decryption)
# Must use the official install script
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
