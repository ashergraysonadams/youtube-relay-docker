import os
import pickle
import subprocess
import time
import re
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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

        proc2.wait()

        _, err1 = proc1.communicate()
        _, err2 = proc2.communicate()

        if err1:
            print(f"🧾 yt-dlp error:\n{err1.decode('utf-8')}")
        if err2:
            print(f"🧾 ffmpeg error:\n{err2.decode('utf-8')}")

    except Exception as e:
        print(f"❌ فشل البث: {e}")

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

    # تنقية وتحويل الروابط لصيغة موحدة
    urls = [clean_url(link) for link in raw_urls if clean_url(link)]

    if not urls:
        print("⚠️ لا توجد روابط صالحة للبث")
        return

    print(f"✅ تم العثور على {len(urls)} رابطاً للبث")
    for url in urls:
        stream_video(url)
        time.sleep(5)

if __name__ == "__main__":
    main()
