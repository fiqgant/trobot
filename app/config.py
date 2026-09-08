"""Central constants for trobot. Adjust here, not scattered through the code."""

# --- Motor GPIO (BCM), per Bot.pdf. R_EN/L_EN wired straight to 3.3V, no pin needed. ---
LEFT_RPWM = 12
LEFT_LPWM = 13
RIGHT_RPWM = 18
RIGHT_LPWM = 19
PWM_FREQ_HZ = 1000

# --- Control loop ---
CONTROL_HZ = 50
CMD_TIMEOUT = 0.5     # s without a manual cmd -> stop (link-loss failsafe)
AUTO_TIMEOUT = 0.5    # s without a fresh auto-follow cmd -> stop (target lost)

# --- Camera / vision ---
CAMERA_INDEX = 0
FRAME_W = 640
FRAME_H = 480
YOLO_MODEL = "yolov8n.pt"
YOLO_CONF = 0.4

# --- Auto-follow P-controller ---
# plain proportional control, no smoothing/PID -- upgrade if it oscillates in practice
AUTO_KP_TURN = 1.2        # bbox dx offset (-1..1) -> vz
AUTO_KP_FWD = 1.5         # bbox area error -> vx
AUTO_TARGET_AREA = 0.15   # desired bbox_area / frame_area ("ideal follow distance")
