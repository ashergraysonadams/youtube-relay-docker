#!/usr/bin/env python3
# coding=utf-8

"""
Stream playlist / videos.txt to YouTube Live.
- Cookies via COOKIES_B64 env var (base64)
- Supports PLAYLIST_ID (via YouTube API) or local videos.txt
- Downloads next video 60s before current ends
"""

import os, base64, pickle, time, re, tempfile
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery   import build
from googleapiclient.errors      import HttpError
import yt_dlp
import subprocess

# ═══════ إعداد البيئة ═══════
TOKEN_PATH    = "creds/token.pickle"
CLIENT_SECRET = "secrets/client_secret.json"
VIDEO_FILE    = "videos.txt"
SCOPES        = ["https://www.googleapis.com/auth/youtube.readonly"]

STREAM_KEY    = os.getenv("STREAM_KEY")
PLAYLIST_ID   = os.getenv("PLAYLIST_ID")
PROXY         = os.getenv("PROXY_URL")

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 11; Pixel 5) "
    "AppleWebKit/537.36 (KHTML, مثل Gecko) Chrome/122 Mobile Safari/537.36"
)

if os.getenv("RENDER") != "true":
    from dotenv import load_dotenv
    load_dotenv()

# ═══════ الكوكيز من COOKIES_B64 ═══════
def decode_cookies():
    b64 = os.getenv("COOKIES_B64", "")
    if not b64:
        raise RuntimeError("❌ COOKIES_B64 غير مضاف.")
    path = tempfile.NamedTemporaryFile(delete=False, suffix=".txt").name
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64))
    return path

COOKIES_FILE = decode_cookies()

# ═══════ إعداد yt-dlp ═══════
yt_opts_base = {
    "cookies": COOKIES_FILE,
    "user_agent": USER_AGENT,
    "format": "bestvideo[height<=720]+bestaudio/best",
    "sleep_interval": 5,
    "max_sleep_interval": 15,
    "retries": 10,
    "progress": False,
    "no_color": True,
    "concurrent_fragment_downloads": 1,
}
if PROXY:
    yt_opts_base["proxy"] = PROXY

# ═══════ وظائف مساعدة ═══════
def authenticate():
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if os.getenv("RENDER") == "true":
            print("⚠️ token.pickle مفقود داخل Render.")
            return None
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
        creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)
    return build("youtube", "v3", credentials=creds)

def playlist_urls(youtube, pid):
    videos, nxt = [], None
    while True:
        res = youtube.playlistItems().list(
            part="contentDetails", playlistId=pid, maxResults=50, pageToken=nxt
        ).execute()
        videos += [
            f"https://www.youtube.com/watch?v={it['contentDetails']['videoId']}"
            for it in res.get("items", [])
        ]
        nxt = res.get("nextPageToken")
        if not nxt:
            break
    return videos

def clean(url: str):
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
    return f"https://www.youtube.com/watch?v={m.group(1)}" if m else None

def video_info(url):
    opts = yt_opts_base | {"quiet": True, "skip_download": True, "forcejson": True}
    try:
        return yt_dlp.YoutubeDL(opts).extract_info(url, download=False)
    except Exception as e:
        print(f"⚠️ تعذّر جلب معلومات {url}: {e}")
        return {"duration": 0}

def prefetch(url, path):
    opts = yt_opts_base | {
        "merge_output_format": "mp4",
        "outtmpl": path,
        "quiet": True,
        "retries": 10,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"❌ فشل تحميل الفيديو {url}: {e}")
        return False

def stream(path_or_url):
    cmd = [
        "ffmpeg", "-re", "-i", path_or_url,
        "-c:v", "libx264", "-preset", "veryfast",
        "-g", "60", "-keyint_min", "60",
        "-c:a", "aac",
        "-f", "flv", f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"
    ]
    print("📤 أمر ffmpeg المستخدم:")
    print(" ".join(cmd))
    return subprocess.Popen(cmd)

# ═══════ الدالة الرئيسية ═══════
def main():
    if not STREAM_KEY:
        print("⚠️ STREAM_KEY غير مضاف.")
        return

    if PLAYLIST_ID:
        yt = authenticate()
        if not yt:
            return
        raw = playlist_urls(yt, PLAYLIST_ID)
    else:
        if not os.path.exists(VIDEO_FILE):
            print("⚠️ videos.txt غير موجود.")
            return
        raw = [l.strip() for l in open(VIDEO_FILE, encoding="utf-8") if l.strip()]

    urls = [u for u in map(clean, raw) if u]
    if not urls:
        print("⚠️ لا توجد روابط صالحة.")
        return
    print(f"✅ عدد الفيديوهات الجاهزة: {len(urls)}")

    cache_dir = tempfile.mkdtemp(prefix="yt_cache_")

    for idx, url in enumerate(urls):
        info     = video_info(url)
        duration = info.get("duration", 0) or 0
        cur_path = os.path.join(cache_dir, f"video_{idx}.mp4")

        if not os.path.exists(cur_path):
            print(f"⬇️ تحميل الفيديو {idx+1}/{len(urls)}")
            success = prefetch(url, cur_path)
            if not success or not os.path.exists(cur_path):
                print(f"❌ فشل حفظ الفيديو: {cur_path}")
                continue

        print(f"🚀 بدء البث: {url}")
        print(f"✅ الملف جاهز: {cur_path}")
        proc_stream = stream(cur_path)

        # تحميل التالي مسبقًا
        if idx + 1 < len(urls):
            next_url  = urls[idx + 1]
            next_path = os.path.join(cache_dir, f"video_{idx+1}.mp4")

            time.sleep(max(duration - 60, 0))

            if not os.path.exists(next_path):
                print("⏳ تحميل الفيديو التالي…")
                prefetch(next_url, next_path)

            time.sleep(60)
        else:
            time.sleep(duration)

        proc_stream.terminate()
        print("✅ انتهى بث الفيديو الحالي.")

    print("🏁 تم بث كل الفيديوهات.")

# ═══════
if __name__ == "__main__":
    main()
