"""
reddit_shorts/parallel.py — Multi-core batch post processing for Ryzen 7900X and similar.

Uses ProcessPoolExecutor to safely parallelize independent post processing jobs.
Respects MAX_PARALLEL_POSTS config and auto-detects optimal worker count.
"""

import os
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
from pathlib import Path
from typing import Optional, Callable, Any

from reddit_shorts import config as cfg
from reddit_shorts.scraper import RedditPost


def get_optimal_worker_count() -> int:
    """
    Calculate optimal number of parallel workers for post processing.
    
    Returns
    -------
    int
        Number of worker processes to use
        
    Notes
    -----
    Each post uses:
    - TTS: ~2-3 CPU-bound chunks (can time-share on 12 cores)
    - Video composition: Full CPU until FFmpeg encode finishes
    
    Safe default: cpu_count() // 3 leaves room for OS and I/O tasks.
    For Ryzen 7900X (12c): 4 parallel posts max, leaving 0 idle.
    """
    if cfg.MAX_PARALLEL_POSTS is not None:
        return max(1, cfg.MAX_PARALLEL_POSTS)
    
    count = cpu_count()
    if count is None:
        count = 4
    
    # Conservative: 1 worker per 3 cores; avoid thrashing
    optimal = max(1, count // 3)
    
    # Cap at 4 (more than 4 causes diminishing returns on typical systems)
    return min(optimal, 4)


def process_batch_parallel(
    posts: list[RedditPost],
    process_fn: Callable[[RedditPost], Optional[Path]],
    max_workers: Optional[int] = None,
) -> dict[str, Optional[Path]]:
    """
    Process multiple posts in parallel using ProcessPoolExecutor.
    
    Parameters
    ----------
    posts : list[RedditPost]
        Reddit posts to process
    process_fn : callable
        Function that takes a RedditPost and returns Path to final video or None.
        Must be picklable (defined at module level or importable).
    max_workers : int, optional
        Number of parallel workers. If None, uses optimal count.
    
    Returns
    -------
    dict[str, Optional[Path]]
        Mapping of post_id → final_video_path (or None if failed/skipped)
    
    Examples
    --------
    >>> from reddit_shorts.pipeline import process_post_standalone
    >>> results = process_batch_parallel(posts, process_post_standalone, max_workers=4)
    >>> for post_id, video_path in results.items():
    ...     if video_path:
    ...         print(f"✓ {post_id}: {video_path}")
    """
    if max_workers is None:
        max_workers = get_optimal_worker_count()
    
    print(f"[parallel] Processing {len(posts)} post(s) with {max_workers} worker(s)")
    
    results = {}
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all jobs
        future_to_post = {
            executor.submit(process_fn, post): post 
            for post in posts
        }
        
        # Collect results as they complete
        completed = 0
        for future in as_completed(future_to_post):
            post = future_to_post[future]
            try:
                video_path = future.result()
                results[post.post_id] = video_path
                completed += 1
                if video_path:
                    print(f"[parallel] [{completed}/{len(posts)}] ✓ {post.post_id}")
                else:
                    print(f"[parallel] [{completed}/{len(posts)}] ⊘ {post.post_id} (skipped)")
            except Exception as exc:
                results[post.post_id] = None
                print(f"[parallel] [{completed}/{len(posts)}] ✗ {post.post_id}")
                print(f"[parallel]   Error: {exc}")
                traceback.print_exc()
    
    return results
