#!/usr/bin/env python3
"""
Minimal yt-dlp API server for FloView.
Returns direct video URLs for any YouTube video.
Deploy on Render.com free tier (Docker with deno).

IMPORTANT: Set YOUTUBE_COOKIES env var with your YouTube cookies
to bypass bot detection. Without cookies, YouTube blocks datacenter IPs.
Export cookies using browser extension "Get cookies.txt LOCALLY"
and paste the content as the YOUTUBE_COOKIES env var.
"""

import json
import os
import subprocess
import sys
import re
import tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler

# CORS - allow FloView origins (and any *.floview.pages.dev subdomain)
ALLOWED_ORIGINS = [
    "https://floview.pages.dev",
    "http://localhost:5173",
    "http://localhost:3000",
]

# Cookie file path (set from YOUTUBE_COOKIES env var)
COOKIE_FILE = None

def _init_cookies():
    """Initialize cookie file from YOUTUBE_COOKIES env var.
    
    Supports three formats:
    1. Base64-encoded Netscape cookies.txt (RECOMMENDED for Render — survives env var pasting)
    2. JSON format with cookie name-value pairs
    3. Raw Netscape cookies.txt content
    
    For Render: encode your cookies file with `base64 cookies.txt` and paste the result.
    """
    global COOKIE_FILE
    cookies = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if not cookies:
        return
    
    # Try base64 decode first (most reliable for Render env vars)
    import base64
    try:
        decoded = base64.b64decode(cookies).decode('utf-8')
        # Check if it looks like valid cookies
        if '.youtube.com' in decoded or '# Netscape' in decoded:
            cookies = decoded
            print(f"[yt-dlp-api] Decoded base64 cookies successfully")
    except Exception:
        pass  # Not base64, try other formats
    
    # Fix: Render env vars may convert newlines to spaces or literal \n
    cookies = cookies.replace("\\n", "\n")
    
    # Fix: Netscape cookie format column 2 is "include_subdomains" (TRUE for .youtube.com)
    # Some exports put httpOnly in column 2 instead, which causes "AssertionError"
    # We need to ensure .youtube.com entries have TRUE in column 2
    # This regex fixes: .youtube.com\tFALSE → .youtube.com\tTRUE
    import re as _re
    cookies = _re.sub(r'(\.youtube\.com)\t(FALSE)\t', r'\1\tTRUE\t', cookies)
    
    # Check if it's JSON format [{name:..., value:...}, ...]
    if cookies.startswith("["):
        try:
            cookie_list = json.loads(cookies)
            lines = ["# Netscape HTTP Cookie File"]
            for c in cookie_list:
                domain = c.get("domain", ".youtube.com")
                path = c.get("path", "/")
                secure = "TRUE" if c.get("secure", True) else "FALSE"
                expiry = c.get("expirationDate", c.get("expiry", 0))
                if isinstance(expiry, float):
                    expiry = int(expiry)
                name = c.get("name", "")
                value = c.get("value", "")
                http_only = "TRUE" if c.get("httpOnly", True) else "FALSE"
                # Netscape format column 2 is "include_subdomains", NOT httpOnly
                # It should be TRUE if domain starts with "." (meaning subdomains included)
                include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
                lines.append(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")
            cookies = "\n".join(lines)
        except json.JSONDecodeError:
            pass  # Not JSON, treat as Netscape format
    
    # Ensure the file starts with the Netscape header
    if not cookies.startswith("#"):
        cookies = "# Netscape HTTP Cookie File\n" + cookies
    
    # Write cookies to a temp file that yt-dlp can read
    COOKIE_FILE = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
    COOKIE_FILE.write(cookies)
    COOKIE_FILE.flush()
    line_count = cookies.count("\n")
    print(f"[yt-dlp-api] Cookies loaded ({len(cookies)} bytes, {line_count} lines)")

_init_cookies()


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
        """Health check and debug endpoint."""
        path = self.path.split('?')[0]
        if path == '/debug':
            # Debug: list available formats for a video
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(self.path).query)
            vid = qs.get('id', [''])[0]
            if not vid:
                self._send_json({"error": "Add ?id=VIDEO_ID to debug"}, 400)
                return
            cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--no-check-certificates", "--list-formats"]
            if COOKIE_FILE:
                cmd += ["--cookies", COOKIE_FILE.name]
            cmd.append(f"https://www.youtube.com/watch?v={vid}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            self._send_json({"stdout": result.stdout[-2000:], "stderr": result.stderr[-500:], "code": result.returncode})
            return
        
        # Check deno availability
        deno_available = False
        try:
            r = subprocess.run(["deno", "--version"], capture_output=True, text=True, timeout=5)
            deno_available = r.returncode == 0
            deno_version = r.stdout.strip()[:50] if deno_available else ""
        except Exception:
            deno_version = ""
        
        self._send_json({
            "service": "floview-ytdlp-api",
            "version": "1.5.2",
            "status": "ok",
            "cookies": "loaded" if COOKIE_FILE else "not_set",
            "deno": deno_available,
            "deno_version": deno_version,
        })

    def _try_ytdlp(self, url, quality, audio_only, extractor_args):
        """Run yt-dlp with specific arguments. Returns (data_dict, error_msg)."""
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-warnings",
            "--no-check-certificates",
            "--quiet",
            "--dump-json",
            "--no-download",
        ]

        # Add cookies if available
        if COOKIE_FILE:
            cmd += ["--cookies", COOKIE_FILE.name]

        # Add extractor args if provided
        cmd.extend(extractor_args)

        # Format selection — yt-dlp needs --merge-output-format for merging
        # video+audio. But we're not downloading — we're just getting URLs.
        # Use format strings that work with --dump-json:
        # 1. Try pre-merged progressive formats (best for direct download)
        # 2. Fall back to best single stream (video only, no merge needed)
        if audio_only:
            cmd += ["-f", "ba/b"]
        else:
            if quality == "360p":
                cmd += ["-f", "b[height<=480]/bv[height<=480]/bv+ba/b"]
            elif quality == "1080p":
                cmd += ["-f", "b[height<=1080]/bv[height<=1080]/bv+ba/b"]
            else:  # 720p default
                cmd += ["-f", "b[height<=720]/bv[height<=720]/bv+ba/b"]

        cmd.append(url)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "yt-dlp failed"
            return None, error_msg

        data = json.loads(result.stdout)
        return data, None

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

        # Extract video ID
        vid_match = re.search(r'(?:v=|youtu\.be/|shorts/|live/)([a-zA-Z0-9_-]{11})', url)
        video_id = vid_match.group(1) if vid_match else ""

        try:
            # Client strategies to try in order
            # If cookies are set, the first strategy usually works
            strategies = [
                ("web", ["--extractor-args", "youtube:player_client=web"]),
                ("mweb", ["--extractor-args", "youtube:player_client=mweb"]),
                ("tv", ["--extractor-args", "youtube:player_client=tv"]),
                ("ios", ["--extractor-args", "youtube:player_client=ios"]),
                ("android", ["--extractor-args", "youtube:player_client=android"]),
                ("default", []),
            ]

            last_error = ""
            data = None
            strategy_used = ""

            for name, extractor_args in strategies:
                sys.stderr.write(f"[yt-dlp-api] Trying {name}...\n")
                data, error = self._try_ytdlp(url, quality, audio_only, extractor_args)

                if data is not None:
                    strategy_used = name
                    sys.stderr.write(f"[yt-dlp-api] {name} succeeded!\n")
                    break

                last_error = error
                # Only retry on bot detection errors
                if "Sign in to confirm" not in error and "bot" not in error.lower():
                    break

                sys.stderr.write(f"[yt-dlp-api] {name} failed: {error[:100]}\n")

            if data is None:
                if "Sign in to confirm" in last_error or "bot" in last_error.lower():
                    self._send_json({"error": "YouTube is temporarily blocking requests. Try again later."}, 503)
                elif "Video unavailable" in last_error:
                    self._send_json({"error": "This video is unavailable."}, 404)
                else:
                    self._send_json({"error": f"Could not get video info: {last_error[:200]}"}, 500)
                return

            # Extract the direct URL
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
                video_url = data.get("url", "")

            # Determine URL type
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
                "proxyable": is_direct,
                "strategy": strategy_used,
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
    print(f"[yt-dlp-api] Cookies: {'loaded' if COOKIE_FILE else 'not set (set YOUTUBE_COOKIES env var)'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[yt-dlp-api] Shutting down")
        server.server_close()


if __name__ == "__main__":
    main()
