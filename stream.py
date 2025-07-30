import os, pickle, subprocess, time
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

TOKEN_PATH = "creds/token.pickle"
CLIENT_SECRET = "secrets/client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
STREAM_KEY = os.getenv("STREAM_KEY")

def authenticate():
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
        creds = flow.run_console()
        os.makedirs("creds", exist_ok=True)
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)
    return build("youtube", "v3", credentials=creds)

def get_playlist_videos(youtube, playlist_id):
    videos = []
    nextPageToken = None
    while True:
        res = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=nextPageToken
        ).execute()
        for item in res["items"]:
            vid = item["contentDetails"]["videoId"]
            videos.append(f"https://www.youtube.com/watch?v={vid}")
        nextPageToken = res.get("nextPageToken")
        if not nextPageToken:
            break
    return videos

def stream_video(url):
    print(f"🎬 بث الفيديو: {url}")
    try:
        proc1 = subprocess.Popen(["yt-dlp", "-f", "best", url, "-o", "-"], stdout=subprocess.PIPE)
        proc2 = subprocess.Popen(["ffmpeg", "-re", "-i", "-", "-f", "flv", f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"], stdin=proc1.stdout)
        proc2.wait()
    except Exception as e:
        print(f"❌ خطأ أثناء البث: {e}")

def main():
    playlist_id = os.getenv("PLAYLIST_ID")
    youtube = authenticate() if playlist_id else None
    urls = get_playlist_videos(youtube, playlist_id) if playlist_id else [
        line.strip() for line in open("videos.txt", "r") if line.strip()
    ]

    while True:
        for url in urls:
            stream_video(url)
            time.sleep(5)

if __name__ == "__main__":
    main()
