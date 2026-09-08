"""FastAPI app: serves the web UI, the MJPEG video stream, and the
control/lock WebSocket. This is the only network-facing surface -- the
ground-control Mac talks to nothing else.
"""
import json
import logging
import os
import threading
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse

from . import control, vision
from .state import SharedState

load_dotenv()  # picks up .env in the project root (GEOAPIFY_API_KEY etc), no-op if absent

log = logging.getLogger("trobot.server")

STATIC_DIR = Path(__file__).parent / "static"
GEOAPIFY_API_KEY = os.environ.get("GEOAPIFY_API_KEY", "")

app = FastAPI()
state = SharedState()
_stop_event = threading.Event()


@app.on_event("startup")
def _start_background_loops():
    threading.Thread(target=vision.run, args=(state, _stop_event), daemon=True).start()
    threading.Thread(target=control.run, args=(state, _stop_event), daemon=True).start()


@app.on_event("shutdown")
def _stop_background_loops():
    _stop_event.set()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/static/style.css")
def style_css():
    return FileResponse(STATIC_DIR / "style.css", media_type="text/css")


@app.get("/static/script.js")
def script_js():
    return FileResponse(STATIC_DIR / "script.js", media_type="application/javascript")


@app.get("/api/map")
def map_proxy(lat: float, lon: float):
    """Server-side static-map proxy: the Geoapify key stays in .env on this
    machine and never reaches the browser or gets committed anywhere."""
    if not GEOAPIFY_API_KEY:
        return Response(status_code=503, content=b"GEOAPIFY_API_KEY not configured")
    url = (
        "https://maps.geoapify.com/v1/staticmap"
        f"?style=osm-bright&width=220&height=130&center=lonlat:{lon},{lat}"
        f"&zoom=12&marker=lonlat:{lon},{lat};color:%23ff0000;size:medium"
        f"&apiKey={GEOAPIFY_API_KEY}"
    )
    try:
        r = requests.get(url, timeout=5)
    except requests.RequestException:
        log.warning("geoapify request failed")
        return Response(status_code=502)
    return Response(content=r.content, media_type=r.headers.get("content-type", "image/png"))


@app.get("/stream")
def stream():
    def gen():
        boundary = b"--frame\r\n"
        while True:
            jpeg = state.get_frame()
            if jpeg is not None:
                yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.03)  # ~30fps cap, avoids busy-looping when frames are slow

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            _handle_message(msg)
    except WebSocketDisconnect:
        log.info("ws client disconnected")


def _handle_message(msg: dict):
    mtype = msg.get("type")
    if mtype == "cmd":
        state.set_manual_cmd(float(msg.get("vx", 0.0)), float(msg.get("vz", 0.0)))
    elif mtype == "click":
        state.request_lock(float(msg["x"]), float(msg["y"]))
    elif mtype == "mode" and msg.get("value") == "manual":
        state.cancel_auto()
    elif mtype == "camera":
        on = msg.get("value") == "on"
        state.set_camera(on)
        if not on:
            state.cancel_auto()  # no video -> nothing to auto-follow
    elif mtype == "detection":
        on = msg.get("value") == "on"
        state.set_detection(on)
        if not on:
            state.cancel_auto()  # no boxes -> nothing to auto-follow
