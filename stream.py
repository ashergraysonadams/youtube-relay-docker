import os
import pickle
import subprocess
import time
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

# تحميل متغيرات البيئة من .env
load_dotenv()

# إعداد المسارات والثوابت
TOKEN_PATH = "creds/token.pickle"
CLIENT_SECRET = "secrets/client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
STREAM_KEY = os.getenv("STREAM_KEY")
PLAYLIST_ID = os.getenv("PLAYLIST_ID")

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

            for item in res.get("items", []):
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
            ["yt-dlp", "-f", "best", "-o", "-", url],
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
        print("⚠️ تأكد من وجود STREAM_KEY في ملف .env")
        return

    if PLAYLIST_ID:
        youtube = authenticate()
        urls = get_playlist_videos(youtube, PLAYLIST_ID)
    else:
        video_file = "videos.txt"
        if not os.path.exists(video_file):
            print("⚠️ ملف videos.txt غير موجود")
            return
        with open(video_file, "r") as f:
            urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print("⚠️ لا توجد روابط للبث")
        return

    while True:
        for url in urls:
            stream_video(url)
            time.sleep(5)  # مدة التوقف بين كل فيديو

if __name__ == "__main__":
    main()
