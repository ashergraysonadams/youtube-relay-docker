from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
import subprocess, sys, os, signal

app = FastAPI()

# سنحتفظ بمعرّف العملية عالمياً لنتحكم فيها
stream_proc: subprocess.Popen | None = None


# 1) إطلاق البث مرّة واحدة لحظة بدء التطبيق
@app.on_event("startup")
async def launch_stream() -> None:
    global stream_proc
    stream_proc = subprocess.Popen(
        [sys.executable, "-u", "stream.py"],  # -u لعرض الـ stdout فوراً
        env=os.environ,                       # يورِّث متغيّرات البيئة لـ stream.py
    )
    print(f"📡 stream.py بدأ PID={stream_proc.pid}")


# 2) إغلاق البث بأمان عند إيقاف الخدمة
@app.on_event("shutdown")
async def stop_stream() -> None:
    if stream_proc and stream_proc.poll() is None:
        print("🛑 إنهاء stream.py")
        stream_proc.terminate()
        try:
            stream_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            stream_proc.kill()
            print("⚠️ stream.py أُجبر على الإغلاق")


# 3) مسار فحص الحالة
@app.get("/")
async def root() -> JSONResponse:
    if not stream_proc:
        return JSONResponse({"status": "not-started"}, status_code=503)

    alive = stream_proc.poll() is None
    return JSONResponse(
        {
            "status": "running" if alive else "stopped",
            "pid": stream_proc.pid,
        },
        status_code=200 if alive else 500,
    )
