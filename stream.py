import os
import pickle
import subprocess
import time
import re
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import yt_dlp

# ✅ في حالة التشغيل المحلي فقط
if os.getenv("RENDER") != "true":
    from dotenv import load_dotenv
    load_dotenv()

# إعداد المسارات والثوابت
TOKEN_PATH     = "creds/token.pickle"
CLIENT_SECRET  = "secrets/client_secret.json"
COOKIES_FILE   = "secrets/cookies.txt"
VIDEO_FILE     = "videos.txt"
SCOPES         = ["https://www.googleapis.com/auth/youtube.readonly"]

# تحميل من البيئة
STREAM_KEY     = os.getenv("STREAM_KEY")
PLAYLIST_ID    = os.getenv("PLAYLIST_ID")

def authenticate():
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if os.getenv("RENDER") == "true":
            print("⚠️ لا يمكن المصادقة اليدوية داخل Render. تأكد من أن token.pickle موجود.")
            return None
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
        creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)

def get_playlist_videos(youtube, playlist_id):
    videos = []
    next_page_token = None
    try:
        while True:
            res = youtube.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            items = res.get("items", [])
            for item in items:
                video_id = item["contentDetails"]["videoId"]
                videos.append(f"https://www.youtube.com/watch?v={video_id}")

            next_page_token = res.get("nextPageToken")
            if not next_page_token:
                break
    except HttpError as e:
        print(f"❌ خطأ من YouTube API: {e}")
    return videos

def clean_url(url):
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    return None

def get_video_duration(url):
    try:
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "forcejson": True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("duration", 0)
    except Exception as e:
        print(f"⚠️ تعذر استخراج مدة الفيديو: {e}")
        return 0

def stream_video(url):
    print(f"\n🎬 بدء البث: {url}\n")
    try:
        proc1 = subprocess.Popen(
            ["yt-dlp", "--cookies", COOKIES_FILE, "-f", "best", "-o", "-", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        proc2 = subprocess.Popen(
            ["ffmpeg", "-re", "-i", "-", "-f", "flv", f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"],
            stdin=proc1.stdout,
            stderr=subprocess.PIPE
        )

        return proc1, proc2

    except Exception as e:
        print(f"❌ فشل البث: {e}")
        return None, None

def main():
    if not STREAM_KEY:
        print("⚠️ STREAM_KEY غير موجود في Render Dashboard")
        return

    if not os.path.exists(COOKIES_FILE):
        print("⚠️ لا يوجد ملف cookies.txt في مجلد secrets/")
        return

    if PLAYLIST_ID:
        youtube = authenticate()
        if youtube is None:
            return
        raw_urls = get_playlist_videos(youtube, PLAYLIST_ID)
    else:
        if not os.path.exists(VIDEO_FILE):
            print("⚠️ ملف videos.txt غير موجود")
            return
        with open(VIDEO_FILE, "r", encoding="utf-8") as f:
            raw_urls = [line.strip() for line in f if line.strip()]

    urls = [clean_url(link) for link in raw_urls if clean_url(link)]

    if not urls:
        print("⚠️ لا توجد روابط صالحة للبث")
        return

    print(f"✅ تم العثور على {len(urls)} رابطاً للبث")

    for i, url in enumerate(urls):
        duration = get_video_duration(url)
        proc1, proc2 = stream_video(url)

        wait_time = duration - 60 if duration > 60 else duration
        time.sleep(wait_time)

        # تجهيز الفيديو القادم قبل نهاية الحالي بدقيقة
        if i + 1 < len(urls):
            print("⏳ تجهيز الفيديو التالي...")
            subprocess.Popen(["yt-dlp", "--cookies", COOKIES_FILE, "-f", "best", "-o", "-", urls[i + 1]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        remaining = 60 if duration > 60 else 0
        time.sleep(remaining)

        if proc1: proc1.terminate()
        if proc2: proc2.terminate()
        print("✅ انتهى البث لهذا الفيديو")

if __name__ == "__main__":
    main()
