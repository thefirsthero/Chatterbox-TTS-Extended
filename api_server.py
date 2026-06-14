"""
api_server.py — FastAPI wrapper for the Reddit Shorts pipeline.

Endpoints:
  POST /generate       — Start async video generation, returns job_id
  GET  /job/{job_id}   — Poll job status (queued → processing → done/error)
  GET  /jobs           — List all jobs
  POST /prefetch       — Prefetch posts from Reddit
  GET  /health         — Health check + queue stats
  GET  /download/{name} — Serve a generated video file
  DELETE /files/{name}  — Delete a generated file after Drive upload
"""

import os
import subprocess
import sys
import uuid
import threading
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Chatterbox Shorts Pipeline")

# ── Paths ──────────────────────────────────────────────────────────
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
VIDEOS_DIR = OUTPUT_DIR / "videos"
CACHE_DIR = OUTPUT_DIR / "cache" / "local_posts"

VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Job System ─────────────────────────────────────────────────────
jobs: Dict[str, dict] = {}
jobs_lock = threading.Lock()


def _run_generate_job(job_id: str):
    """Background thread for video generation."""
    with jobs_lock:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        cmd = [sys.executable, "/app/run_shorts_pipeline.py", "--local-posts", "--max", "1"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd="/app")

        if result.returncode != 0:
            with jobs_lock:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = (result.stderr or result.stdout)[-500:]
            return

        # Find the newest video
        videos = sorted(VIDEOS_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if videos:
            video = videos[0]
            stdout = result.stdout
            post_id = "unknown"
            for line in stdout.splitlines():
                if "Processing post:" in line:
                    post_id = line.split(":")[-1].strip()[:12]
                    break

            with jobs_lock:
                jobs[job_id]["status"] = "done"
                jobs[job_id]["file_name"] = video.name
                jobs[job_id]["file_path"] = str(video)
                jobs[job_id]["post_id"] = post_id
                jobs[job_id]["log"] = stdout[-1000:] if stdout else None
        else:
            with jobs_lock:
                jobs[job_id]["status"] = "skipped"
                jobs[job_id]["error"] = "Pipeline completed but no video produced."

    except subprocess.TimeoutExpired:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "Generation timed out (10 min limit)."
    except Exception as e:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)
    finally:
        with jobs_lock:
            jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()


# ── Models ─────────────────────────────────────────────────────────
class GenerateResponse(BaseModel):
    job_id: str
    status: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    post_id: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class PrefetchResponse(BaseModel):
    status: str
    count: int
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    cached_posts: int
    generated_videos: int
    active_jobs: int
    disk_free_gb: float


# ── Helpers ────────────────────────────────────────────────────────
def get_cached_post_count() -> int:
    if not CACHE_DIR.exists():
        return 0
    return len(list(CACHE_DIR.glob("*.json")))


def get_generated_video_count() -> int:
    if not VIDEOS_DIR.exists():
        return 0
    return len(list(VIDEOS_DIR.glob("*.mp4")))


def active_job_count() -> int:
    with jobs_lock:
        return sum(1 for j in jobs.values() if j["status"] in ("queued", "processing"))


# ── Endpoints ──────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health():
    disk = __import__("shutil").disk_usage(OUTPUT_DIR)
    return HealthResponse(
        status="healthy",
        cached_posts=get_cached_post_count(),
        generated_videos=get_generated_video_count(),
        active_jobs=active_job_count(),
        disk_free_gb=round(disk.free / (1024**3), 1),
    )


@app.post("/generate", response_model=GenerateResponse)
async def generate():
    """Start async video generation. Returns job_id immediately."""
    cached = get_cached_post_count()
    if cached == 0:
        raise HTTPException(status_code=400, detail="No cached posts. Run /prefetch first.")

    job_id = str(uuid.uuid4())[:8]
    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file_name": None,
            "file_path": None,
            "post_id": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
        }

    thread = threading.Thread(target=_run_generate_job, args=(job_id,), daemon=True)
    thread.start()

    return GenerateResponse(job_id=job_id, status="queued")


@app.get("/job/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Poll job status."""
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job)


@app.get("/jobs")
async def list_jobs():
    """List all jobs."""
    with jobs_lock:
        return list(jobs.values())


@app.post("/prefetch", response_model=PrefetchResponse)
async def prefetch(count: int = 20):
    """Prefetch posts from Reddit into local cache."""
    try:
        cmd = [sys.executable, "/app/run_shorts_pipeline.py", "--prefetch-local-posts", "--prefetch-count", str(count)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd="/app")
        if result.returncode != 0:
            return PrefetchResponse(status="error", count=0, error=(result.stderr or "Unknown error")[-300:])
        return PrefetchResponse(status="done", count=get_cached_post_count())
    except subprocess.TimeoutExpired:
        return PrefetchResponse(status="error", count=0, error="Prefetch timed out.")
    except Exception as e:
        return PrefetchResponse(status="error", count=0, error=str(e))


@app.get("/download/{file_name}")
async def download(file_name: str):
    """Serve a generated video file."""
    file_path = VIDEOS_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(file_path), media_type="video/mp4", filename=file_name)


@app.delete("/files/{file_name}")
async def delete_file(file_name: str):
    """Delete a generated file after Drive upload."""
    file_path = VIDEOS_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    return {"status": "deleted", "file_name": file_name}


# ── Startup ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"Pipeline API starting on port 8000")
    print(f"   Output dir: {OUTPUT_DIR}")
    print(f"   Cached posts: {get_cached_post_count()}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
