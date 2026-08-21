# FloView yt-dlp API — Deployment Guide

This is the backend that powers FloView's video downloads. It uses yt-dlp to extract direct video URLs from YouTube, which FloView then streams through its `/api/stream` proxy.

## One-Time Setup (5 minutes)

### Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Name it `fv-ytdlp-api`
3. Make it **Private**
4. Don't initialize with README
5. Click "Create repository"

### Step 2: Push the Code

```bash
cd FloView/yt-dlp-api
git remote add origin https://github.com/YOUR_USERNAME/fv-ytdlp-api.git
git push -u origin master
```

### Step 3: Deploy on Render.com (FREE)

1. Go to https://render.com and sign up with GitHub
2. Click **"New +"** → **"Web Service"**
3. Connect your `fv-ytdlp-api` repository
4. Settings:
   - **Name**: `fv-ytdlp-api`
   - **Runtime**: Docker
   - **Region**: Oregon (closest to YouTube servers)
   - **Instance Type**: Free
   - **Docker Build Context**: `.`
5. Click **"Create Web Service"**
6. Wait for build to complete (~2-3 min)
7. Note your service URL: `https://fv-ytdlp-api.onrender.com`

### Step 4: Verify

```bash
# Test the API
curl -X POST https://fv-ytdlp-api.onrender.com \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","quality":"720p"}'
```

Expected response:
```json
{
  "url": "https://rr2---sn-xxx.googlevideo.com/videoplayback?...",
  "title": "Rick Astley - Never Gonna Give You Up",
  "duration": 213,
  "filesize": 12345678,
  "isDirect": true,
  "proxyable": true
}
```

## How It Works

```
User clicks Download on FloView
  ↓
DownloadManager tries:
  1. Stored Piped proxy URL (for LBRY videos)
  2. Fresh Piped URL from /api/download
  3. yt-dlp API → direct googlevideo.com URL  ← THIS IS THE FIX
  4. Honest failure if all fail
  ↓
Stream URL goes through /api/stream proxy
  ↓
Full video downloads to user's device
```

## Notes

- **Render free tier**: Service sleeps after 15 min of inactivity. First request after sleep takes ~30s (cold start). Subsequent requests are instant.
- **Deno**: The Docker image installs deno, which yt-dlp needs for n-parameter decryption. Without deno, yt-dlp falls back to VISIONOS client which only returns HLS manifests.
- **Rate limits**: YouTube may rate-limit the server IP. If this happens, yt-dlp will return an error and FloView will show a "try again later" message.
- **Cost**: $0/month on Render free tier (750 hours/month, 512MB RAM).
