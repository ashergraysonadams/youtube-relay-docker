import os
import pickle
import subprocess
import time
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ✅ في حالة التشغيل المحلي فقط: يمكن تحميل من ملف .env
if os.getenv("RENDER") != "true":
    from dotenv import load_dotenv
    load_dotenv()

# إعداد المسارات والثوابت
TOKEN_PATH     = "creds/token.pickle"
CLIENT_SECRET  = "secrets/client_secret.json"
COOKIES_FILE   = "secrets/cookies.txt"
VIDEO_FILE     = "videos.txt"
SCOPES         = ["https://www.googleapis.com/auth/youtube.readonly"]

# 📦 تحميل القيم من متغيرات البيئة (Render Dashboard)
STREAM_KEY     = os.getenv("STREAM_KEY")
PLAYLIST_ID    = os.getenv("PLAYLIST_ID")

def authenticate():
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
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
        print(f"❌ خطأ في استدعاء YouTube API: {e}")
    return videos

def stream_video(url):
    print(f"\n🎬 بدء البث: {url}\n")
    try:
        proc1 = subprocess.Popen(
            ["yt-dlp", "--cookies", COOKIES_FILE, "-f", "best", "-o", "-", url],
            stdout=subprocess.PIPE
        )

        proc2 = subprocess.Popen(
            ["ffmpeg", "-re", "-i", "-", "-f", "flv", f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"],
            stdin=proc1.stdout
        )

        proc2.wait()
    except Exception as e:
        print(f"❌ خطأ أثناء البث: {e}")

def main():
    if not STREAM_KEY:
        print("⚠️ STREAM_KEY غير معرف في البيئة - تأكد من إضافته في Render Dashboard")
        return

    if not os.path.exists(COOKIES_FILE):
        print("⚠️ ملف الكوكيز غير موجود: secrets/cookies.txt")
        return

    if PLAYLIST_ID:
        youtube = authenticate()
        urls = get_playlist_videos(youtube, PLAYLIST_ID)
    else:
        if not os.path.exists(VIDEO_FILE):
            print("⚠️ ملف videos.txt غير موجود")
            return
        with open(VIDEO_FILE, "r") as f:
            urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print("⚠️ لا توجد روابط للبث")
        return

    for url in urls:
        stream_video(url)
        time.sleep(5)

if __name__ == "__main__":
    main()
