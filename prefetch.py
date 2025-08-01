import subprocess, os, base64

COOKIES_FILE = "cookies.txt"
USER_AGENT = "Mozilla/5.0"
yt_opts_base = {
    "format": "best"
}

def write_cookies_file():
    """تفريغ محتوى COOKIES_B64 داخل ملف cookies.txt مؤقتًا"""
    cookies_b64 = os.getenv("COOKIES_B64")
    if cookies_b64:
        cookies_raw = base64.b64decode(cookies_b64.encode()).decode()
        with open(COOKIES_FILE, "w") as f:
            f.write(cookies_raw)

def prefetch(url, path):
    """تنزيل الفيديو عبر yt-dlp باستخدام بروكسي فقط أثناء التحميل"""
    write_cookies_file()  # ← تأكد من وجود cookies.txt أولًا

    cmd = [
        "yt-dlp", "-f", yt_opts_base["format"], "--merge-output-format", "mp4",
        "--cookies", COOKIES_FILE, "--user-agent", USER_AGENT,
        "-o", path, url, "--quiet", "--retries", "10"
    ]

    proxy = os.getenv("PROXY_URL")
    if proxy:
        cmd += ["--proxy", proxy]

    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
