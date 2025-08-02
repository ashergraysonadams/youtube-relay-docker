from fastapi import FastAPI
import subprocess

app = FastAPI()

@app.get("/")
def start_stream():
    subprocess.Popen(["python3", "stream.py"])
    return {"status": "stream started"}
