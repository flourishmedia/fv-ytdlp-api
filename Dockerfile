FROM python:3.12-slim

# Install ffmpeg (REQUIRED by yt-dlp for merging video+audio streams)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

# Install deno (for yt-dlp n-parameter decryption)
RUN curl -fsSL https://deno.land/install.sh | sh 2>/dev/null || true
ENV PATH="/root/.deno/bin:${PATH}"

# Install yt-dlp
RUN pip install --no-cache-dir yt-dlp

WORKDIR /app
COPY server.py .

EXPOSE 8080

CMD ["python", "server.py", "8080"]
