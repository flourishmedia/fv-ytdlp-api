FROM python:3.12-slim

# Install ffmpeg and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install deno (required by yt-dlp for n-parameter decryption)
RUN curl -fsSL https://deno.land/install.sh | sh || true
ENV PATH="/root/.deno/bin:${PATH}"

# Install yt-dlp
RUN pip install --no-cache-dir yt-dlp

WORKDIR /app
COPY server.py .

EXPOSE 8080

CMD ["python", "server.py", "8080"]
