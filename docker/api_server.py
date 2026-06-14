"""
api_server.py — FastAPI wrapper for the Reddit Shorts pipeline.

Endpoints:
  POST /generate       — Generate one video from cached posts
  GET  /health         — Health check + queue stats
  POST /prefetch       — Prefetch posts from Reddit
  GET  /download/{name} — Serve a generated video file
  DELETE /files/{name}  — Delete a generated file after upload
"""

import os
import subprocess
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Chatterbox Shorts Pipeline")

# ── Paths ──────────────────────────────────────────────────────────
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
VIDEOS_DIR = OUTPUT_DIR / "videos"
CACHE_DIR = OUTPUT_DIR / "cache" / "local_posts"

VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ── Models ─────────────────────────────────────────────────────────
class GenerateResponse(BaseModel):
    status: str
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    post_id: Optional[str] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None


class PrefetchResponse(BaseModel):
    status: str
    count: int
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    cached_posts: int
    generated_videos: int
    disk_free_gb: float


# ── Helpers ────────────────────────────────────────────────────────
def run_pipeline(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    """Run the pipeline script with arguments."""
    cmd = [sys.executable, "/app/run_shorts_pipeline.py"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd="/app")


def get_cached_post_count() -> int:
    """Count how many cached local posts are available."""
    if not CACHE_DIR.exists():
        return 0
    return len(list(CACHE_DIR.glob("*.json")))


def get_generated_video_count() -> int:
    """Count generated videos."""
    if not VIDEOS_DIR.exists():
        return 0
    return len(list(VIDEOS_DIR.glob("*.mp4")))


# ── Endpoints ──────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check with queue statistics."""
    disk = shutil.disk_usage(OUTPUT_DIR)
    return HealthResponse(
        status="healthy",
        cached_posts=get_cached_post_count(),
        generated_videos=get_generated_video_count(),
        disk_free_gb=round(disk.free / (1024**3), 1),
    )


@app.post("/generate", response_model=GenerateResponse)
async def generate():
    """Generate one video from local cached posts (--local-posts --max 1)."""
    cached = get_cached_post_count()
    if cached == 0:
        return GenerateResponse(
            status="skipped",
            error="No cached posts available. Run /prefetch first.",
        )

    try:
        result = run_pipeline("--local-posts", "--max", "1")
        if result.returncode != 0:
            return GenerateResponse(
                status="error",
                error=result.stderr[-500:] if result.stderr else result.stdout[-500:],
            )

        # Find the newest video file
        videos = sorted(VIDEOS_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if videos:
            video = videos[0]
            # Try to extract post_id from filename or output
            stdout = result.stdout
            post_id = "unknown"
            for line in stdout.splitlines():
                if "post_id" in line.lower() or "Processing" in line:
                    import re
                    m = re.search(r'[0-9a-zA-Z]{6,8}', line)
                    if m:
                        post_id = m.group(0)
                        break

            return GenerateResponse(
                status="done",
                file_name=video.name,
                file_path=str(video),
                post_id=post_id,
                duration_seconds=round(timeout if result.returncode == 0 else 0, 1),
            )

        return GenerateResponse(
            status="skipped",
            error="Pipeline completed but no video was produced (post may have been filtered out).",
        )

    except subprocess.TimeoutExpired:
        return GenerateResponse(status="error", error="Generation timed out (10 min limit).")
    except Exception as e:
        return GenerateResponse(status="error", error=str(e))


@app.post("/prefetch", response_model=PrefetchResponse)
async def prefetch(count: int = 20):
    """Prefetch posts from Reddit into local cache."""
    try:
        result = run_pipeline("--prefetch-local-posts", "--prefetch-count", str(count))
        if result.returncode != 0:
            return PrefetchResponse(
                status="error",
                count=0,
                error=result.stderr[-300:] if result.stderr else "Unknown error",
            )

        return PrefetchResponse(
            status="done",
            count=get_cached_post_count(),
        )

    except subprocess.TimeoutExpired:
        return PrefetchResponse(status="error", count=0, error="Prefetch timed out.")
    except Exception as e:
        return PrefetchResponse(status="error", count=0, error=str(e))


@app.get("/download/{file_name}")
async def download(file_name: str):
    """Serve a generated video file for n8n to download."""
    file_path = VIDEOS_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=file_name,
    )


@app.delete("/files/{file_name}")
async def delete_file(file_name: str):
    """Delete a generated file after n8n uploads it to Drive."""
    file_path = VIDEOS_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    return {"status": "deleted", "file_name": file_name}


# ── Startup ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Pipeline API starting on port 8000")
    print(f"   Output dir: {OUTPUT_DIR}")
    print(f"   Cached posts: {get_cached_post_count()}")
    print(f"   Generated videos: {get_generated_video_count()}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
