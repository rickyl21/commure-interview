import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

app = FastAPI()

MAX_UPLOAD_BYTES = 200 * 1024 * 1024

# External transform service config; the token stays server-side only.
TRANSFORM_BASE_URL = os.environ.get("TRANSFORM_BASE_URL", "")
TRANSFORM_TOKEN = os.environ.get("TRANSFORM_TOKEN", "")
TRANSFORM_TIMEOUT_S = 120.0

# Per-clip limits of the transform API (see PLAN.md "API Constraints").
MAX_CLIP_SECONDS = 10.0
MAX_CLIP_BYTES = 3_000_000
MAX_CLIP_FRAMES = 600
MAX_CLIP_WIDTH, MAX_CLIP_HEIGHT = 1920, 1080
# Budget for frame data per clip; the rest is headroom for MP4 container overhead.
CLIP_PAYLOAD_BYTES = 2_900_000

# Max transform API calls in flight across all uploads (they share one token), and retries per clip.
TRANSFORM_CONCURRENCY = 3
TRANSFORM_RETRIES = 2
_transform_slots = threading.Semaphore(TRANSFORM_CONCURRENCY)


def to_grayscale(input_path: Path, output_path: Path) -> Path:
    """POST an MP4 to the external /api/transform and save the grayscale MP4 it returns."""
    if not TRANSFORM_BASE_URL or not TRANSFORM_TOKEN:
        raise RuntimeError("TRANSFORM_BASE_URL and TRANSFORM_TOKEN must be set")

    with input_path.open("rb") as f:
        res = httpx.post(
            f"{TRANSFORM_BASE_URL.rstrip('/')}/api/transform",
            headers={"Authorization": f"Bearer {TRANSFORM_TOKEN}"},
            files={"clip": (input_path.name, f, "video/mp4")},
            timeout=TRANSFORM_TIMEOUT_S,
        )
    res.raise_for_status()

    output_path.write_bytes(res.content)
    return output_path


def _ffprobe(path: Path, *args: str) -> dict:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-of", "json", *args, str(path)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise ValueError("Could not read video: file is not a valid MP4")
    return json.loads(res.stdout)


def needs_split(input_path: Path) -> bool:
    """True if the video exceeds any single-clip limit of the transform API (duration, frames, bytes)."""
    info = _ffprobe(input_path, "-count_packets", "-show_entries", "stream=nb_read_packets:format=duration")
    if not info.get("streams"):
        raise ValueError("File has no video stream")
    duration = float(info["format"]["duration"])
    frames = int(info["streams"][0]["nb_read_packets"])
    return (
        duration > MAX_CLIP_SECONDS
        or frames > MAX_CLIP_FRAMES
        or input_path.stat().st_size > MAX_CLIP_BYTES
    )

def split_video(input_path: Path, out_dir: Path) -> list[Path]:
    """Split an MP4 into video-only clips that each fit the transform API's limits.

    Cuts are planned from per-frame sizes so every clip is <= 10 s, <= 600 frames and
    under the byte limit, then made with stream copy (no re-encode) at keyframes.
    Raises ValueError if the video is unsupported or can't be split to fit.
    """
    streams = _ffprobe(input_path, "-show_entries", "stream=codec_name,width,height")["streams"]
    if not streams:
        raise ValueError("File has no video stream")
    s = streams[0]
    if s.get("codec_name") != "h264":
        raise ValueError(f"Video must be H.264 (got {s.get('codec_name')})")
    if s["width"] > MAX_CLIP_WIDTH or s["height"] > MAX_CLIP_HEIGHT:
        raise ValueError(f"Video is {s['width']}x{s['height']}; maximum is {MAX_CLIP_WIDTH}x{MAX_CLIP_HEIGHT}")

    packets = _ffprobe(input_path, "-show_entries", "packet=pts_time,duration_time,size,flags")["packets"]
    if not packets:
        raise ValueError("Video has no frames")

    # Group frames into GOPs (keyframe + following frames); stream copy can only cut at their starts.
    gops: list[dict] = []
    end_time = 0.0
    for p in packets:
        pts = float(p.get("pts_time", "nan"))
        if "K" in p.get("flags", "") or not gops:
            gops.append({"start": pts, "bytes": 0, "frames": 0})
        gops[-1]["bytes"] += int(p["size"])
        gops[-1]["frames"] += 1
        end_time = max(end_time, pts + float(p.get("duration_time", 0)))
    for g, nxt in zip(gops, gops[1:] + [{"start": end_time}]):
        g["seconds"] = nxt["start"] - g["start"]

    # Greedily pack whole GOPs into clips without crossing any limit.
    cut_times: list[float] = []
    clip = {"bytes": 0, "frames": 0, "seconds": 0.0}
    for g in gops:
        if g["bytes"] > CLIP_PAYLOAD_BYTES or g["frames"] > MAX_CLIP_FRAMES or g["seconds"] > MAX_CLIP_SECONDS:
            raise ValueError(
                f"Can't split: the segment at {g['start']:.2f}s between keyframes is "
                f"{g['seconds']:.2f}s, {g['frames']} frames, {g['bytes']:,} bytes, over the per-clip limit"
            )
        fits = (
            clip["bytes"] + g["bytes"] <= CLIP_PAYLOAD_BYTES
            and clip["frames"] + g["frames"] <= MAX_CLIP_FRAMES
            and clip["seconds"] + g["seconds"] <= MAX_CLIP_SECONDS
        )
        if clip["frames"] and not fits:
            cut_times.append(g["start"])
            clip = {"bytes": 0, "frames": 0, "seconds": 0.0}
        for k in clip:
            clip[k] += g[k]

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(input_path), "-map", "0:v:0", "-an", "-c", "copy"]
    if cut_times:
        # Nudge each cut slightly earlier so float rounding can't skip past the target keyframe.
        times = ",".join(f"{t - 0.001:.6f}" for t in cut_times)
        cmd += ["-f", "segment", "-segment_times", times, "-reset_timestamps", "1", str(out_dir / "seg_%03d.mp4")]
    else:
        cmd += [str(out_dir / "seg_000.mp4")]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg split failed: {res.stderr.strip()}")

    clips = sorted(out_dir.glob("seg_*.mp4"))
    if len(clips) != len(cut_times) + 1:
        raise RuntimeError(f"Expected {len(cut_times) + 1} clips, ffmpeg produced {len(clips)}")
    for c in clips:
        if c.stat().st_size > MAX_CLIP_BYTES:
            raise RuntimeError(f"{c.name} is {c.stat().st_size:,} bytes, over the {MAX_CLIP_BYTES:,} limit")
    return clips


@dataclass
class Segment:
    """One clip of a split video; `index` fixes its place when the results are rejoined."""
    index: int
    src: Path  # clip sent to the API (seg_NNN.mp4)
    out: Path  # grayscale clip returned by the API (out_NNN.mp4)
    frames: int  # frame count of src; the API result must match
    status: str = "pending"  # pending | sending | done | failed
    attempts: int = 0


def _frame_count(path: Path) -> int:
    info = _ffprobe(path, "-count_packets", "-show_entries", "stream=nb_read_packets")
    return int(info["streams"][0]["nb_read_packets"])


def _transform_segment(seg: Segment) -> None:
    """Send one clip to the API, retrying transient failures, and check the result's frame count."""
    while True:
        seg.attempts += 1
        seg.status = "sending"
        try:
            with _transform_slots:
                to_grayscale(seg.src, seg.out)
            break
        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as e:
            # 4xx (bad token, rejected clip) won't succeed on retry; 5xx, timeouts and network errors might.
            transient = not isinstance(e, httpx.HTTPStatusError) or e.response.status_code >= 500
            if not transient or seg.attempts > TRANSFORM_RETRIES:
                seg.status = "failed"
                raise
            time.sleep(seg.attempts)

    try:
        got = _frame_count(seg.out)
    except ValueError as e:  # unreadable API output is an upstream fault, not a bad upload
        seg.status = "failed"
        raise RuntimeError(f"Segment {seg.index}: API returned an unreadable video ({e})")
    if got != seg.frames:
        seg.status = "failed"
        raise RuntimeError(f"Segment {seg.index}: API returned {got} frames, expected {seg.frames}")
    seg.status = "done"


def concat_clips(clips: list[Path], output_path: Path) -> Path:
    """Join clips in the given order with stream copy (they all come from the same API encoder)."""
    list_file = output_path.with_suffix(".txt")
    list_file.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    res = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c", "copy", "-movflags", "+faststart", str(output_path)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {res.stderr.strip()}")
    return output_path


def grayscale_video(input_path: Path, work_dir: Path, output_path: Path) -> Path:
    """Split into API-sized clips, transform them in parallel, and rejoin them in index order."""
    clips = split_video(input_path, work_dir / "segments")
    segments = [
        Segment(i, p, work_dir / "segments" / f"out_{i:03d}.mp4", _frame_count(p))
        for i, p in enumerate(clips)
    ]

    with ThreadPoolExecutor(max_workers=TRANSFORM_CONCURRENCY) as pool:
        # list() re-raises the first segment failure.
        list(pool.map(_transform_segment, segments))

    concat_clips([s.out for s in sorted(segments, key=lambda s: s.index)], output_path)

    expected = sum(s.frames for s in segments)
    got = _frame_count(output_path)
    if got != expected:
        raise RuntimeError(f"Rejoined video has {got} frames, expected {expected}")
    return output_path


# async so the raw body can be streamed to disk; the blocking pipeline runs in a thread.
@app.post("/api/grayscale")
async def grayscale(request: Request) -> FileResponse:
    if request.headers.get("content-type") != "video/mp4":
        raise HTTPException(400, "Upload must be an MP4 (Content-Type: video/mp4)")

    work_dir = Path(tempfile.mkdtemp(prefix="grayscale-"))
    input_path = work_dir / "input.mp4"
    output_path = work_dir / "grayscale.mp4"
    try:
        size = 0
        with input_path.open("wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Video is larger than 200 MB")
                f.write(chunk)
        if size == 0:
            raise HTTPException(400, "Uploaded file is empty")

        try:
            await run_in_threadpool(grayscale_video, input_path, work_dir, output_path)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except RuntimeError as e:
            raise HTTPException(500, str(e))
        except httpx.TimeoutException:
            raise HTTPException(504, "Transform service timed out")
        except httpx.HTTPStatusError as e:
            raise HTTPException(502, f"Transform service returned {e.response.status_code}")
        except httpx.RequestError:
            raise HTTPException(502, "Could not reach transform service")
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename="grayscale.mp4",
        background=BackgroundTask(shutil.rmtree, work_dir, ignore_errors=True),
    )
