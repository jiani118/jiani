import os
import re
import shutil
import tempfile
import threading
import time
import uuid

import yt_dlp
from flask import Flask, after_this_request, jsonify, request, send_file, send_from_directory

app = Flask(__name__, static_folder=None)
URL_RE = re.compile(r"^https?://", re.I)
HAS_FFMPEG = shutil.which("ffmpeg") is not None


@app.get("/")
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "index.html")


# 常用网站：extractor 名称前缀（小写）-> (显示名, 中文名, 徽章颜色)
POPULAR = [
    ("youtube", "YouTube", "油管", "#e5322d"),
    ("bilibili", "BiliBili", "哔哩哔哩（B站）", "#00a1d6"),
    ("douyin", "Douyin", "抖音", "#161823"),
    ("tiktok", "TikTok", "TikTok", "#161823"),
    ("twitter", "X / Twitter", "推特", "#1d9bf0"),
    ("instagram", "Instagram", "Instagram", "#c13584"),
    ("facebook", "Facebook", "脸书", "#1877f2"),
    ("vimeo", "Vimeo", "Vimeo", "#1ab7ea"),
    ("twitch", "Twitch", "Twitch", "#9146ff"),
    ("reddit", "Reddit", "Reddit", "#ff4500"),
    ("dailymotion", "Dailymotion", "Dailymotion", "#0066dc"),
    ("soundcloud", "SoundCloud", "SoundCloud", "#ff5500"),
    ("bandcamp", "Bandcamp", "Bandcamp", "#1da0c3"),
    ("niconico", "niconico", "Niconico", "#555555"),
    ("weibo", "Weibo", "微博", "#e6162d"),
    ("acfun", "AcFun", "A站", "#fd4c5d"),
]

_CACHE = {}


def _load_sites():
    if _CACHE:
        return _CACHE
    from yt_dlp.extractor import list_extractor_classes

    names = sorted(
        {
            ie.IE_NAME.split(":")[0]
            for ie in list_extractor_classes()
            if ie.IE_DESC is not False and ie.IE_NAME != "generic"
        },
        key=str.lower,
    )
    lower = [n.lower() for n in names]
    # 只展示当前 yt-dlp 里确实存在的常用网站
    popular = [
        {"key": k, "name": n, "zh": zh, "color": c}
        for k, n, zh, c in POPULAR
        if any(x.startswith(k) for x in lower)
    ]
    zh_map = {p["key"]: p["zh"] for p in popular}
    _CACHE.update(sites=names, popular=popular, zh=zh_map)
    return _CACHE


PWA_FILES = {"manifest.json", "sw.js", "icon-192.png", "icon-512.png"}


@app.get("/<name>")
def pwa_file(name):
    if name not in PWA_FILES:
        return jsonify(error="not found"), 404
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), name)


@app.get("/api/sites")
def sites():
    data = _load_sites()
    return jsonify(version=yt_dlp.version.__version__, **data)


@app.post("/api/info")
def info():
    url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
    if not URL_RE.match(url):
        return jsonify(error="请输入有效的视频链接"), 400
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
            d = ydl.extract_info(url, download=False)
        heights = sorted(
            {f["height"] for f in d.get("formats", [])
             if f.get("height") and f.get("vcodec") not in (None, "none")},
            reverse=True,
        )
        return jsonify(
            heights=heights,
            has_ffmpeg=HAS_FFMPEG,
            title=d.get("title"),
            thumbnail=d.get("thumbnail"),
            duration=d.get("duration"),
            uploader=d.get("uploader"),
        )
    except Exception as e:
        return jsonify(error="解析失败：" + str(e)[:200]), 400


JOBS = {}
JOBS_LOCK = threading.Lock()
SLOTS = threading.Semaphore(3)  # 同时最多 3 个下载任务
JOB_TTL = 30 * 60  # 任务和临时文件保留 30 分钟


def _cleanup_old():
    now = time.time()
    with JOBS_LOCK:
        old = [i for i, j in JOBS.items() if now - j["ts"] > JOB_TTL]
        for i in old:
            shutil.rmtree(JOBS[i]["tmp"], ignore_errors=True)
            del JOBS[i]


def _format_for(kind, height):
    if kind == "audio":
        return "bestaudio/best"
    if height and HAS_FFMPEG:
        return f"bv*[height<={height}]+ba/b[height<={height}]/b"
    if height:
        return f"b[height<={height}][ext=mp4]/b[height<={height}]/b"
    return "bv*+ba/b" if HAS_FFMPEG else "b[ext=mp4]/b"


def _run(job_id, url, kind, height):
    job = JOBS[job_id]

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            job["status"] = "downloading"
            job["percent"] = round(d["downloaded_bytes"] / total * 100, 1) if total else None
            job["speed"] = d.get("speed")
            job["eta"] = d.get("eta")
        elif d["status"] == "finished":
            job["status"] = "processing"
            job["percent"] = 100

    opts = {
        "quiet": True,
        "noplaylist": True,
        "outtmpl": os.path.join(job["tmp"], "%(title).80s.%(ext)s"),
        "format": _format_for(kind, height),
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
    }
    with SLOTS:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(url, download=True)
            files = [
                os.path.join(job["tmp"], f)
                for f in os.listdir(job["tmp"])
                if not f.endswith((".part", ".ytdl"))
            ]
            if not files:
                raise RuntimeError("没有生成文件")
            job["file"] = max(files, key=os.path.getsize)
            job["status"] = "done"
        except Exception as e:
            job["status"] = "error"
            job["error"] = "下载失败：" + str(e)[:200]


@app.post("/api/start")
def start():
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    kind = body.get("type", "video")
    height = str(body.get("height") or "")
    height = int(height) if height.isdigit() else None
    if not URL_RE.match(url):
        return jsonify(error="链接无效"), 400

    _cleanup_old()
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "status": "queued", "percent": 0, "speed": None, "eta": None,
        "file": None, "error": None, "ts": time.time(),
        "tmp": tempfile.mkdtemp(),
    }
    threading.Thread(target=_run, args=(job_id, url, kind, height), daemon=True).start()
    return jsonify(id=job_id)


@app.get("/api/progress/<job_id>")
def progress(job_id):
    j = JOBS.get(job_id)
    if not j:
        return jsonify(error="任务不存在或已过期"), 404
    return jsonify({k: j[k] for k in ("status", "percent", "speed", "eta", "error")})


@app.get("/api/file/<job_id>")
def get_file(job_id):
    j = JOBS.get(job_id)
    if not j or j["status"] != "done":
        return jsonify(error="文件未就绪或已过期"), 404

    @after_this_request
    def cleanup(resp):
        shutil.rmtree(j["tmp"], ignore_errors=True)
        JOBS.pop(job_id, None)
        return resp

    return send_file(j["file"], as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
