"""TRACE live demo server (T10).

    .venv/Scripts/python.exe app/server.py            then open http://127.0.0.1:8000

Everything runs on this machine. The browser talks to 127.0.0.1 only: it
receives a small preview image and numbers, never raw video.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from engine import LiveEngine  # noqa: E402
from biofeedback import PulseController, demo_state  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
app = FastAPI(title="TRACE live")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
engine = LiveEngine()


@app.get("/")
def index():
    # Never cache the page: a demo machine must always load the current build.
    return FileResponse(STATIC / "game.html", headers={"Cache-Control": "no-store"})


@app.get("/lab")
def legacy_lab():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/lab")
def lab():
    """Compression-lab data built by scripts/build_app_assets.py from the grid."""
    p = STATIC / "lab" / "lab.json"
    if not p.exists():
        return JSONResponse({"available": False,
                             "message": "Run the grid and scripts/build_app_assets.py to fill the compression lab."})
    return JSONResponse({"available": True, **json.loads(p.read_text())})


@app.get("/video.mjpg")
async def video():
    async def gen():
        last = None
        while True:
            frame = engine.jpeg
            if frame and frame is not last:
                last = frame
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            await asyncio.sleep(1 / 15)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    controller = PulseController()
    mode = "engine"
    scenario = "cycle"
    started = time.monotonic()
    last_frame = None
    last_fresh = time.monotonic()

    async def reader():
        nonlocal mode, scenario, started
        while True:
            msg = json.loads(await sock.receive_text())
            cmd = msg.get("cmd")
            if cmd == "start":
                mode = "engine"
                controller.reset()
                await asyncio.to_thread(engine.start, msg.get("source", "sim"), **msg.get("options", {}))
            elif cmd == "demo":
                mode = "demo"
                scenario = "cycle"
                started = time.monotonic()
                controller.reset()
            elif cmd == "scenario":
                if msg.get("value") in ("cycle", "steady", "elevated", "scare", "dropout"):
                    scenario = msg["value"]
            elif cmd == "calibrate":
                controller.reset()
            elif cmd == "stop":
                await asyncio.to_thread(engine.stop)
            elif cmd == "hrv_start":
                engine.hrv_begin()
            elif cmd == "hrv_finish":
                result = await asyncio.to_thread(engine.hrv_finish)
                await sock.send_text(json.dumps({"type": "hrv", "result": result}))

    task = asyncio.create_task(reader())
    try:
        while not task.done():
            now = time.monotonic()
            state = demo_state(now - started, scenario) if mode == "demo" else dict(engine.state)
            if mode == "engine":
                if state.get("t") != last_frame:
                    last_frame, last_fresh = state.get("t"), now
                if now - last_fresh > 2:
                    state = {**state, "confident": False, "error": "Video data is stale"}
            state["feedback"] = controller.update(state, now)
            await sock.send_text(json.dumps({"type": "state", "state": state}, allow_nan=False))
            await asyncio.sleep(0.12)
        task.result()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        task.cancel()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    print(f"TRACE live: open http://127.0.0.1:{args.port}")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
