#!/usr/bin/env python3
"""
Minimal yt-dlp API server for FloView.
Returns direct video URLs for any YouTube video.
Deploy on Render.com free tier (Docker with deno).
"""

import json
import subprocess
import sys
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

# CORS - allow FloView origins (and any *.floview.pages.dev subdomain)
ALLOWED_ORIGINS = [
    "https://floview.pages.dev",
    "http://localhost:5173",
    "http://localhost:3000",
]

class YtdlpHandler(BaseHTTPRequestHandler):
    def _send_cors(self):
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS or ".floview.pages.dev" in origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        """Health check endpoint."""
        self._send_json({
            "service": "floview-ytdlp-api",
            "version": "1.0.0",
            "status": "ok",
        })

    def do_POST(self):
        """Get direct video URL from a YouTube URL using yt-dlp."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            self._send_json({"error": "Invalid JSON body"}, 400)
            return

        url = body.get("url", "")
        quality = body.get("quality", "720p")
        audio_only = body.get("audioOnly", False)

        if not url:
            self._send_json({"error": "Missing 'url' field"}, 400)
            return

        # Validate it's a YouTube URL
        yt_patterns = [
            r"youtube\.com/watch\?v=",
            r"youtu\.be/",
            r"youtube\.com/shorts/",
            r"youtube\.com/live/",
        ]
        if not any(re.search(p, url) for p in yt_patterns):
            self._send_json({"error": "Only YouTube URLs are supported"}, 400)
            return

        # Extract video ID for the response
        vid_match = re.search(r'(?:v=|youtu\.be/|shorts/|live/)([a-zA-Z0-9_-]{11})', url)
        video_id = vid_match.group(1) if vid_match else ""

        try:
            # Build yt-dlp command
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--no-warnings",
                "--no-check-certificates",
                "--quiet",
                "--dump-json",
                "--no-download",
            ]

            # Format selection
            if audio_only:
                cmd += ["-f", "bestaudio/best"]
            else:
                # Prefer progressive (direct MP4 with audio), then best adaptive
                if quality == "360p":
                    cmd += ["-f", "18/bestvideo+bestaudio/best"]
                elif quality == "1080p":
                    cmd += ["-f", "22/bestvideo+bestaudio/best"]
                else:  # 720p default
                    cmd += ["-f", "22/18/bestvideo+bestaudio/best"]

            cmd.append(url)

            # Run yt-dlp
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or "yt-dlp failed"
                if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
                    self._send_json({"error": "YouTube is temporarily blocking requests. Try again later."}, 503)
                elif "Video unavailable" in error_msg:
                    self._send_json({"error": "This video is unavailable."}, 404)
                else:
                    self._send_json({"error": f"Could not get video info: {error_msg[:200]}"}, 500)
                return

            data = json.loads(result.stdout)

            # Extract the direct URL
            # For merged formats (bestvideo+bestaudio), yt-dlp returns requested_formats
            formats = data.get("requested_formats") or []
            video_url = ""
            audio_url = ""

            if formats:
                for f in formats:
                    furl = f.get("url", "")
                    is_video = f.get("vcodec", "none") != "none"
                    is_audio = f.get("acodec", "none") != "none"
                    if is_video and not video_url:
                        video_url = furl
                    if is_audio and not audio_url:
                        audio_url = furl
            else:
                # Single format (progressive)
                video_url = data.get("url", "")

            # Determine if we got direct URLs or HLS manifests
            is_hls = "manifest.googlevideo.com" in video_url or ".m3u8" in video_url
            is_direct = "googlevideo.com/videoplayback" in video_url

            # Get file size
            filesize = 0
            for f in formats:
                fs = f.get("filesize") or f.get("filesize_approx") or 0
                filesize += fs
            if not filesize:
                filesize = data.get("filesize") or data.get("filesize_approx") or 0

            self._send_json({
                "url": video_url,
                "audioUrl": audio_url,
                "videoId": video_id,
                "title": data.get("title", ""),
                "duration": data.get("duration", 0),
                "thumbnail": data.get("thumbnail", ""),
                "filesize": filesize,
                "format": data.get("format", ""),
                "mimeType": data.get("ext", "mp4"),
                "isHls": is_hls,
                "isDirect": is_direct,
                "proxyable": is_direct,  # Direct URLs can be proxied through /api/stream
            })

        except subprocess.TimeoutExpired:
            self._send_json({"error": "Request timed out"}, 504)
        except json.JSONDecodeError:
            self._send_json({"error": "Could not parse yt-dlp output"}, 500)
        except Exception as e:
            self._send_json({"error": f"Server error: {str(e)[:200]}"}, 500)

    def log_message(self, format, *args):
        """Reduce log noise."""
        if "/favicon" not in format % args:
            sys.stderr.write(f"[yt-dlp-api] {format % args}\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = HTTPServer(("0.0.0.0", port), YtdlpHandler)
    print(f"[yt-dlp-api] Running on port {port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[yt-dlp-api] Shutting down")
        server.server_close()


if __name__ == "__main__":
    main()
