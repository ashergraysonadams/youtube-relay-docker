#!/usr/bin/env python3
# coding=utf-8
"""
Stream playlist / videos.txt to YouTube Live.
– cookies taken from COOKIES_B64 (base64 string in env)
– supports PLAYLIST_ID (YouTube API) أو ملف videos.txt
– pre-downloads next video 60 s before current ends
"""

import os, base64, pickle, subprocess, time, re, tempfile, random
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery   import build
from googleapiclient.errors      import HttpError
import yt_dlp

# ══════════════ 1) ثوابت ومتغيّرات البيئة ═════════════════
TOKEN_PATH   = "creds/token.pickle"
CLIENT_SECRET= "secrets/client_secret.json"
VIDEO_FILE   = "videos.txt"
SCOPES       = ["https://www.googleapis.com/auth/youtube.readonly"]

STREAM_KEY   = os.getenv("STREAM_KEY")
PLAYLIST_ID  = os.getenv("PLAYLIST_ID")
PROXY        = os.getenv("PROXY_URL")

USER_AGENT   = (
    "Mozilla/5.0 (Linux; Android 11; Pixel 5) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Mobile Safari/537.36"
)

if os.getenv("RENDER") != "true":
    from dotenv import load_dotenv
    load_dotenv()

# ══════════════ 2) فكّ الكوكيز من COOKIES_B64 ═════════════
def decode_cookies():
    b64 = os.getenv("COOKIES_B64", "")
    if not b64:
        raise RuntimeError("❌ COOKIES_B64 غير مضاف في البيئة.")
    path = tempfile.NamedTemporaryFile(delete=False, suffix=".txt").name
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64))
    return path

COOKIES_FILE = decode_cookies()

# ══════════════ 3) إعداد خيارات yt-dlp الافتراضيّة ════════
yt_opts_base = {
    "cookies":      COOKIES_FILE,
    "user_agent":   USER_AGENT,
    "format":       "bestvideo[height<=720]+bestaudio/best",
    "sleep_interval":       5,
    "max_sleep_interval":   15,
    "retries":      10,
    "progress":     False,
    "no_color":     True,
    "concurrent_fragment_downloads": 1,
}
if PROXY:
    yt_opts_base["proxy"] = PROXY

# ══════════════ 4) وظائف مساعدة ═══════════════════════════
def authenticate():
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if os.getenv("RENDER") == "true":
            print("⚠️  token.pickle مفقود داخل Render.")
            return None
        flow  = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
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
        print(f"⚠️  تعذّر جلب معلومات {url}: {e}")
        return {"duration": 0}

def prefetch(url, path):
    """تنزيل الفيديو القادم بخلفيّة صامتة (mp4)"""
    cmd = [
        "yt-dlp", "-f", yt_opts_base["format"], "--merge-output-format", "mp4",
        "--cookies", COOKIES_FILE, "--user-agent", USER_AGENT,
        "-o", path, url, "--quiet", "--retries", "10",
    ]
    if PROXY:
        cmd += ["--proxy", PROXY]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

def stream(path_or_url):
    """بث ملف/رابط مباشرةً إلى YouTube Live"""
    cmd = [
        "ffmpeg", "-re", "-i", path_or_url,
        "-c:v", "copy", "-c:a", "aac",
        "-f", "flv", f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

# ══════════════ 5) الدالة الرئيسة ═════════════════════════
def main():
    if not STREAM_KEY:
        print("⚠️  STREAM_KEY غير مضاف في البيئة")
        return

    # ❶ تحضير قائمة الروابط
    if PLAYLIST_ID:
        yt = authenticate()
        if not yt:
            return
        raw = playlist_urls(yt, PLAYLIST_ID)
    else:
        if not os.path.exists(VIDEO_FILE):
            print("⚠️  videos.txt غير موجود")
            return
        raw = [l.strip() for l in open(VIDEO_FILE, encoding="utf-8") if l.strip()]

    urls = [u for u in map(clean, raw) if u]
    if not urls:
        print("⚠️  لا توجد روابط صالحة")
        return
    print(f"✅ {len(urls)} فيديو جاهز للبث")

    # ❷ مجلّد مؤقّت للفيديوهات المسبقة
    cache_dir = tempfile.mkdtemp(prefix="yt_cache_")
    pre_dl_proc = None

    for idx, url in enumerate(urls):
        info     = video_info(url)
        duration = info.get("duration", 0) or 0
        cur_path = os.path.join(cache_dir, f"video_{idx}.mp4")

        # حمّل الملف إن لم يكن موجودًا
        if not os.path.exists(cur_path):
            print(f"⬇️  تنزيل الفيديو {idx+1}/{len(urls)}")
            prefetch(url, cur_path).wait()

        # أبـدأ البث
        print(f"🚀 بدء البث: {url}")
        proc_stream = stream(cur_path)

        # حضّر الفيديو التالي
        if idx + 1 < len(urls):
            next_url  = urls[idx + 1]
            next_path = os.path.join(cache_dir, f"video_{idx+1}.mp4")
            time.sleep(max(duration - 60, 0))   # انتظر حتى دقيقة قبل النهاية

            if not os.path.exists(next_path):
                print("⏳ تنزيل الفيديو التالي…")
                pre_dl_proc = prefetch(next_url, next_path)
        else:
            # آخر فيديو
            time.sleep(duration)

        # انتظر آخر 60 ثانية أو صفر
        time.sleep(60 if duration > 60 else 0)

        # أوقف البث
        proc_stream.terminate()
        print("✅ انتهى بث الفيديو الحالي")

        # تأكد من اكتمال أي تحميل معلق
        if pre_dl_proc:
            pre_dl_proc.wait()
            pre_dl_proc = None

    print("🏁 تم بث جميع الفيديوهات بنجاح")

# ══════════════
if __name__ == "__main__":
    main()
