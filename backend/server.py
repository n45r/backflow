from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
PORT = 8765

app = FastAPI()
(ROOT / "runs").mkdir(exist_ok=True)
app.mount("/runs", StaticFiles(directory=ROOT / "runs"), name="runs")
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")


def main():
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
