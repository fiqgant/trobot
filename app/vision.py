"""Vision loop: camera capture, YOLOv8n tracking, auto-follow steering,
and MJPEG overlay frame production. Runs in its own thread so a slow
inference frame never blocks the motor control loop.
"""
import logging
import threading
import time

import cv2
import numpy as np

from . import config

log = logging.getLogger("trobot.vision")

try:
    from ultralytics import YOLO
    _HAS_YOLO = True
except ImportError:
    _HAS_YOLO = False
    log.warning("ultralytics not available -> object detection disabled, streaming raw camera only")


def _center_and_area(xyxy):
    x1, y1, x2, y2 = xyxy
    return ((x1 + x2) / 2, (y1 + y2) / 2), (x2 - x1) * (y2 - y1)


def _camera_off_frame():
    frame = np.zeros((config.FRAME_H, config.FRAME_W, 3), dtype="uint8")
    text = "CAMERA OFF"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
    x, y = (config.FRAME_W - tw) // 2, (config.FRAME_H + th) // 2
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (90, 90, 90), 2)
    ok, jpeg = cv2.imencode(".jpg", frame)
    return jpeg.tobytes() if ok else None


def run(state, stop_event: threading.Event):
    model = YOLO(config.YOLO_MODEL) if _HAS_YOLO else None
    cap = None

    while not stop_event.is_set():
        if not state.camera_on:
            if cap is not None:
                cap.release()
                cap = None
                state.set_frame(_camera_off_frame())
            time.sleep(0.2)
            continue

        if cap is None:
            cap = cv2.VideoCapture(config.CAMERA_INDEX)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_H)
            if not cap.isOpened():
                log.error("camera index %s failed to open", config.CAMERA_INDEX)
                cap = None
                time.sleep(1.0)
                continue

        ok, frame = cap.read()
        if not ok:
            log.warning("camera read failed, retrying")
            time.sleep(0.1)
            continue

        h, w = frame.shape[:2]
        click = state.pop_pending_click()  # discard silently if detection is off below

        if state.detection_on and model is not None:
            result = model.track(frame, persist=True, verbose=False, conf=config.YOLO_CONF)[0]
            boxes = result.boxes
            locked_id = state.locked_track_id
            locked_box = None

            if boxes is not None and boxes.id is not None:
                ids = boxes.id.int().tolist()
                xyxys = boxes.xyxy.tolist()

                if click is not None:
                    cx, cy = click[0] * w, click[1] * h
                    best_id, best_dist = None, None
                    for tid, xyxy in zip(ids, xyxys):
                        (bx, by), _ = _center_and_area(xyxy)
                        d = (bx - cx) ** 2 + (by - cy) ** 2
                        if best_dist is None or d < best_dist:
                            best_dist, best_id = d, tid
                    if best_id is not None:
                        state.set_lock(best_id)
                        locked_id = best_id

                for tid, xyxy, cls_idx, conf in zip(
                    ids, xyxys, boxes.cls.int().tolist(), boxes.conf.tolist()
                ):
                    is_locked = tid == locked_id
                    if is_locked:
                        locked_box = xyxy
                    color = (0, 0, 255) if is_locked else (0, 200, 0)
                    thickness = 3 if is_locked else 1
                    x1, y1, x2, y2 = map(int, xyxy)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
                    label = f"{model.names[cls_idx]} #{tid} {conf:.2f}"
                    cv2.putText(frame, label, (x1, max(0, y1 - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            if locked_box is not None:
                (bx, by), area = _center_and_area(locked_box)
                dx = (bx - w / 2) / (w / 2)          # -1..1, + = target right of center
                area_ratio = area / (w * h)
                # plain P-controller, no smoothing/PID -- upgrade if it oscillates in practice
                vz = max(-1.0, min(1.0, config.AUTO_KP_TURN * dx))
                vx = max(-1.0, min(1.0, config.AUTO_KP_FWD * (config.AUTO_TARGET_AREA - area_ratio)))
                state.set_auto_cmd(vx, vz)
            # else: locked target not in this frame -> don't refresh auto_ts,
            # control loop's watchdog stops the robot once AUTO_TIMEOUT elapses.
        # else: detection is off -> stream the raw frame untouched, no inference cost.

        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            state.set_frame(jpeg.tobytes())

    if cap is not None:
        cap.release()
