#!/usr/bin/env python3
# coding=utf-8
"""
Stream playlist / videos.txt to YouTube Live – نسخة مُنقّحة لبيئة Render المجانية
───────────────────────────────────────────────────────────────────────────────
• يدعم PLAYLIST_ID أو videos.txt
• لا يبدأ البث إلا بعد اكتمال تحميل الفيديو
• يبدأ تحميل الفيديو التالي فقط بعد انتهاء بث الحالي
• يدعم COOKIES بصيغة base64 من المتغيّر البيئي
"""

import os, base64, pickle, time, re, tempfile, subprocess, sys
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import yt_dlp

# ── ثوابت ───────────────────────────────────────────────────────────────────
TOKEN_PATH, CLIENT_SECRET = "creds/token.pickle", "secrets/client_secret.json"
VIDEO_FILE, SCOPES        = "videos.txt", ["https://www.googleapis.com/auth/youtube.readonly"]

STREAM_KEY   = os.getenv("STREAM_KEY")          # مفتاح البث من يوتيوب
PLAYLIST_ID  = os.getenv("PLAYLIST_ID")         # ID قائمة التشغيل إن وُجدت
PROXY        = os.getenv("PROXY_URL")           # وكيل إن احتجت
FREE_MODE    = os.getenv("FREE_RENDER_MODE", "true").lower() == "true"
BUFFER_DELAY = int(os.getenv("STREAM_DELAY", "60"))

USER_AGENT = ("Mozilla/5.0 (Linux; Android 11; Pixel 5) "
              "AppleWebKit/537.36 (KHTML, مثل Gecko) Chrome/122 Mobile Safari/537.36")

# ﹀ إذا كنت تطوّر محليًا فعّل متغيّرات البيئة من .env
if os.getenv("RENDER") != "true":
    from dotenv import load_dotenv
    load_dotenv()

# ── فكّ الكوكيز من المتغيّر البيئي ──────────────────────────────────────────
def decode_cookies() -> str:
    b64 = os.getenv("COOKIES_B64", "")
    if not b64:
        print("❌ يجب ضبط COOKIES_B64"), sys.exit(1)
    path = tempfile.NamedTemporaryFile(delete=False, suffix=".txt").name
    with open(path, "wb") as fp:
        fp.write(base64.b64decode(b64))
    return path

COOKIES_FILE = decode_cookies()

# ── إعداد yt-dlp الأساسي ───────────────────────────────────────────────────
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

# ── المصادقة لجلب قائمة التشغيل (عند الحاجة) ───────────────────────────────
def authenticate():
    if not PLAYLIST_ID:
        return None
    creds = pickle.load(open(TOKEN_PATH, "rb")) if os.path.exists(TOKEN_PATH) else None
    if not creds or not creds.valid:
        if os.getenv("RENDER") == "true":
            print("⚠️ token.pickle مفقود داخل Render – لن تُجلب القائمة تلقائيًا.")
            return None
        flow  = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
        creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        pickle.dump(creds, open(TOKEN_PATH, "wb"))
    return build("youtube", "v3", credentials=creds)

def playlist_urls(y, pid):
    vids, nxt = [], None
    while True:
        res = y.playlistItems().list(part="contentDetails",
                                     playlistId=pid,
                                     maxResults=50,
                                     pageToken=nxt).execute()
        vids += [f"https://www.youtube.com/watch?v={it['contentDetails']['videoId']}"
                 for it in res["items"]]
        nxt = res.get("nextPageToken")
        if not nxt:
            break
    return vids

# ── أدوات مساعدة ──────────────────────────────────────────────────────────
def clean(u):
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", u)
    return f"https://www.youtube.com/watch?v={m.group(1)}" if m else None

def video_info(u):
    try:
        return yt_dlp.YoutubeDL(
            yt_opts_base | {"quiet": True, "skip_download": True, "forcejson": True}
        ).extract_info(u, download=False)
    except Exception as e:
        print(f"⚠️ تعذّر جلب معلومات {u}: {e}")
        return {"duration": 0}

def prefetch(u, path):
    opts = yt_opts_base | {"merge_output_format": "mp4",
                           "outtmpl": path,
                           "quiet": True}
    try:
        yt_dlp.YoutubeDL(opts).download([u])
        return True
    except Exception as e:
        print(f"❌ فشل تحميل {u}: {e}")
        return False

# ── 🚀 بناء أمر FFmpeg مع معالجة keyint بشكل صحيح ─────────────────────────
def build_ffmpeg_cmd(path):
    if FREE_MODE:
        vf, preset, vb, ab, fps = "scale=-2:360,fps=24", "ultrafast", "700k", "64k", 24
    else:
        vf, preset, vb, ab, fps = "scale=-2:720,fps=30", "veryfast", "2500k", "128k", 30

    buf   = str(int(vb.rstrip("k")) * 2) + "k"
    gop   = str(fps * 4)  # مفتاح إطار كل ~4 ثوانٍ

    return [
        "ffmpeg", "-re", "-i", path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", preset,
        "-tune", "zerolatency",
        "-b:v", vb,
        "-maxrate", vb,
        "-bufsize", buf,

        # ★★ التصحيح الأساسي: ‑x264-params بدلاً من -keyint
        "-x264-params", f"keyint={gop}:min-keyint={gop}:scenecut=0",

        "-g", gop,              # نسخ طول GOP أيضاً على مستوى FFmpeg
        "-sc_threshold", "0",   # تعطيل Scene-Cut أيضاً من جانب FFmpeg

        "-c:a", "aac",
        "-b:a", ab,
        "-f", "flv",
        f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"
    ]

def stream(path):
    cmd = build_ffmpeg_cmd(path)
    print("📤 FFmpeg:", " ".join(cmd))
    return subprocess.Popen(cmd)

# ── الحلقة الرئيسية ────────────────────────────────────────────────────────
def main():
    if not STREAM_KEY:
        print("❌ STREAM_KEY مفقود."), sys.exit(1)

    if PLAYLIST_ID:
        yt = authenticate()
        raw = playlist_urls(yt, PLAYLIST_ID) if yt else []
    else:
        if not os.path.exists(VIDEO_FILE):
            print("❌ videos.txt غير موجود."), sys.exit(1)
        raw = [l.strip() for l in open(VIDEO_FILE, encoding="utf-8") if l.strip()]

    urls = list(filter(None, map(clean, raw)))
    if not urls:
        print("❌ لا توجد روابط صالحة."), sys.exit(1)

    print(f"✅ سيتم بث {len(urls)} فيديو(هات).")
    cache = tempfile.mkdtemp(prefix="ytcache_")

    for i, url in enumerate(urls):
        path = os.path.join(cache, f"v{i}.mp4")

        # تحميل إن لم يكن مُسبقًا
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

        # تحميل الفيديو التالي أثناء الانتظار
        if i + 1 < len(urls):
            next_path = os.path.join(cache, f"v{i+1}.mp4")
            if not os.path.exists(next_path):
                print(f"⬇️ تحميل الفيديو التالي {i+2}")
                prefetch(urls[i+1], next_path)

    print("🏁 اكتمل بث جميع الفيديوهات بنجاح.")

if __name__ == "__main__":
    main()
