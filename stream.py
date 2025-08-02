#!/usr/bin/env python3
# coding=utf-8
"""
Stream playlist / videos.txt to YouTube Live – نسخة مرتّبة لخوادم Render المجانية
---------------------------------------------------------------------------
• يدعم PLAYLIST_ID أو videos.txt
• لا يبدأ البث إلا بعد اكتمال تحميل الفيديو
• يبدأ تحميل الفيديو التالي فقط بعد انتهاء بث الحالي
• يدعم COOKIES بصيغة base64 من env
"""

import os, base64, pickle, time, re, tempfile, subprocess
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import yt_dlp

# ── إعدادات ثابتة ──────────────────────────────────────────────────────────
TOKEN_PATH, CLIENT_SECRET = "creds/token.pickle", "secrets/client_secret.json"
VIDEO_FILE, SCOPES        = "videos.txt", ["https://www.googleapis.com/auth/youtube.readonly"]
STREAM_KEY                = os.getenv("STREAM_KEY")
PLAYLIST_ID               = os.getenv("PLAYLIST_ID")
PROXY                     = os.getenv("PROXY_URL")
FREE_RENDER_MODE          = os.getenv("FREE_RENDER_MODE", "true").lower() == "true"
BUFFER_DELAY              = int(os.getenv("STREAM_DELAY", "60"))
USER_AGENT                = ("Mozilla/5.0 (Linux; Android 11; Pixel 5) "
                             "AppleWebKit/537.36 (KHTML, مثل Gecko) Chrome/122 Mobile Safari/537.36")

if os.getenv("RENDER") != "true":
    from dotenv import load_dotenv
    load_dotenv()

def decode_cookies() -> str:
    b64 = os.getenv("COOKIES_B64", "")
    if not b64:
        raise RuntimeError("❌ COOKIES_B64 غير مضاف.")
    path = tempfile.NamedTemporaryFile(delete=False, suffix=".txt").name
    open(path, "wb").write(base64.b64decode(b64))
    return path

COOKIES_FILE = decode_cookies()

yt_opts_base = {
    "cookies": COOKIES_FILE,
    "user_agent": USER_AGENT,
    "format": "bestvideo[height<=720]+bestaudio/best",
    "sleep_interval": 5,
    "max_sleep_interval": 15,
    "retries": 8,
    "progress": False,
    "no_color": True,
}
if PROXY:
    yt_opts_base["proxy"] = PROXY

def authenticate():
    if not PLAYLIST_ID:
        return None
    creds = pickle.load(open(TOKEN_PATH, "rb")) if os.path.exists(TOKEN_PATH) else None
    if not creds or not creds.valid:
        if os.getenv("RENDER") == "true":
            print("⚠️ token.pickle مفقود داخل Render.")
            return None
        flow  = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
        creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        pickle.dump(creds, open(TOKEN_PATH, "wb"))
    return build("youtube", "v3", credentials=creds)

def playlist_urls(y, pid):
    vids, nxt = [], None
    while True:
        res = y.playlistItems().list(part="contentDetails", playlistId=pid,
                                     maxResults=50, pageToken=nxt).execute()
        vids += [f"https://www.youtube.com/watch?v={it['contentDetails']['videoId']}"
                 for it in res["items"]]
        nxt = res.get("nextPageToken")
        if not nxt: break
    return vids

def clean(u):
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", u)
    return f"https://www.youtube.com/watch?v={m.group(1)}" if m else None

def video_info(u):
    try:
        return yt_dlp.YoutubeDL(yt_opts_base | {"quiet": True, "skip_download": True, "forcejson": True}).extract_info(u, download=False)
    except Exception as e:
        print(f"⚠️ تعذّر معلومات {u}: {e}")
        return {"duration": 0}

def prefetch(u, path):
    opts = yt_opts_base | {"merge_output_format": "mp4", "outtmpl": path, "quiet": True}
    try:
        yt_dlp.YoutubeDL(opts).download([u]); return True
    except Exception as e:
        print(f"❌ فشل تحميل {u}: {e}"); return False

# ── 🚀 أهم تعديل: إضافة -keyint / -g / -sc_threshold ───────────────────────
def build_ffmpeg_cmd(path):
    if FREE_RENDER_MODE:
        vf, preset, vb, ab, fps = "scale=-2:360,fps=24", "ultrafast", "700k", "64k", 24
    else:
        vf, preset, vb, ab, fps = "scale=-2:720,fps=30", "veryfast", "2500k", "128k", 30

    buf   = str(int(vb.rstrip("k")) * 2) + "k"
    gop   = str(fps * 4)  # keyframe كل 4 ثوانٍ
    return [
        "ffmpeg", "-re", "-i", path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", preset, "-tune", "zerolatency",
        "-b:v", vb, "-maxrate", vb, "-bufsize", buf,
        "-keyint", gop, "-g", gop, "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", ab,
        "-f", "flv", f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"
    ]

def stream(path):
    cmd = build_ffmpeg_cmd(path)
    print("📤 FFmpeg:", " ".join(cmd))
    return subprocess.Popen(cmd)

def main():
    if not STREAM_KEY:
        return print("⚠️ STREAM_KEY غير مضاف.")

    if PLAYLIST_ID:
        yt = authenticate()
        raw = playlist_urls(yt, PLAYLIST_ID)
    else:
        if not os.path.exists(VIDEO_FILE):
            return print("⚠️ videos.txt غير موجود.")
        raw = [l.strip() for l in open(VIDEO_FILE, encoding="utf-8") if l.strip()]
    urls = list(filter(None, map(clean, raw)))
    if not urls:
        return print("⚠️ لا روابط صالحة.")
    print(f"✅ سنبث {len(urls)} فيديو(هات).")

    cache = tempfile.mkdtemp(prefix="ytcache_")

    for i, url in enumerate(urls):
        path = os.path.join(cache, f"v{i}.mp4")

        # تحميل الفيديو قبل أي شيء
        if not os.path.exists(path):
            print(f"⬇️ تحميل الفيديو {i+1}")
            if not prefetch(url, path):
                continue

        dur = video_info(url).get("duration", 0) or 0

        print(f"⏳ بَفر {BUFFER_DELAY}s قبل البث…")
        time.sleep(BUFFER_DELAY)

        proc = stream(path)
        print(f"🚀 بدأ البث للفيديو {i+1}")
        time.sleep(dur)
        proc.terminate()
        print("✅ انتهى بث الفيديو.")

        # تحميل التالي بعد انتهاء البث
        if i + 1 < len(urls):
            next_path = os.path.join(cache, f"v{i+1}.mp4")
            if not os.path.exists(next_path):
                print(f"⬇️ تحميل الفيديو التالي {i+2}")
                prefetch(urls[i+1], next_path)

    print("🏁 تم بث جميع الفيديوهات بنجاح.")

if __name__ == "__main__":
    main()
