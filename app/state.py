"""Shared state connecting the three control sources (web-manual, browser
joystick via Gamepad API, auto-follow) to the motor control loop, plus the
latest camera frame for the MJPEG stream.

One lock guards everything -- this is read/written a few times per frame at
50Hz, not a hot path worth splitting into finer-grained locks.
"""
import threading
import time

MANUAL = "manual"
AUTO = "auto"


class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self.mode = MANUAL
        self.manual_vx = 0.0
        self.manual_vz = 0.0
        self.last_cmd_ts = 0.0
        self.locked_track_id = None
        self.pending_click = None  # (x_ratio, y_ratio) in 0..1, set by /ws, consumed by vision loop
        self.auto_vx = 0.0
        self.auto_vz = 0.0
        self.auto_ts = 0.0
        self.latest_jpeg = None
        self.camera_on = True
        self.detection_on = True

    # ---- called from the /ws handler ----

    def set_manual_cmd(self, vx: float, vz: float):
        """Any manual cmd (virtual stick or physical joystick via Gamepad API)
        immediately takes over -- this is the failsafe override rule."""
        with self._lock:
            self.mode = MANUAL
            self.manual_vx = vx
            self.manual_vz = vz
            self.last_cmd_ts = time.time()
            self.locked_track_id = None

    def request_lock(self, x_ratio: float, y_ratio: float):
        with self._lock:
            self.pending_click = (x_ratio, y_ratio)
            self.mode = AUTO

    def cancel_auto(self):
        with self._lock:
            self.mode = MANUAL
            self.locked_track_id = None

    def set_camera(self, on: bool):
        with self._lock:
            self.camera_on = on

    def set_detection(self, on: bool):
        with self._lock:
            self.detection_on = on

    # ---- called from the vision loop ----

    def pop_pending_click(self):
        with self._lock:
            click, self.pending_click = self.pending_click, None
            return click

    def set_lock(self, track_id):
        with self._lock:
            self.locked_track_id = track_id

    def set_auto_cmd(self, vx: float, vz: float):
        with self._lock:
            self.auto_vx = vx
            self.auto_vz = vz
            self.auto_ts = time.time()

    def set_frame(self, jpeg_bytes: bytes):
        with self._lock:
            self.latest_jpeg = jpeg_bytes

    # ---- called from the control loop ----

    def get_drive_target(self, cmd_timeout: float, auto_timeout: float):
        """(vx, vz) the control loop should apply right now. Both failsafe
        timeouts (link loss, target lost) are enforced here."""
        with self._lock:
            now = time.time()
            if self.mode == AUTO:
                if self.locked_track_id is None or (now - self.auto_ts) > auto_timeout:
                    return 0.0, 0.0
                return self.auto_vx, self.auto_vz
            if (now - self.last_cmd_ts) > cmd_timeout:
                return 0.0, 0.0
            return self.manual_vx, self.manual_vz

    # ---- called from the /stream handler ----

    def get_frame(self):
        with self._lock:
            return self.latest_jpeg
