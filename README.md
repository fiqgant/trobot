# trobot

Differential-drive robot on Pi4 + 2x BTS7960, controlled from a browser (web
virtual stick or physical HID joystick via Gamepad API) or auto-follow mode
(click an object in the video → YOLOv8n tracks it, robot follows).

## Architecture

```
Mac (ground control, browser)  <-- WebSocket + MJPEG -->  Pi4 (robot)
  - video stream + click-to-lock                            - FastAPI server
  - virtual joystick                                         - mode_arbiter (state.py)
  - physical joystick via Gamepad API                        - control_loop -> BTS7960 PWM
                                                              - vision_loop -> YOLOv8n .track()
```

- Any manual input (virtual stick or physical joystick) always overrides
  auto-follow immediately — safety rule, no mode switch needed.
- Link-loss failsafe: no command for 0.5s -> motors stop.
- Target-lost failsafe: locked object missing for 0.5s -> motors stop.

See `Bot.pdf` for the BTS7960/UBEC wiring diagram this pin mapping follows.

## Setup

Copy `.env.example` to `.env` and fill in a free API key from
[geoapify.com](https://www.geoapify.com/) (used for the ground-control
location map). `.env` is gitignored — never commit it.

```bash
cp .env.example .env
# then edit .env and paste your key
```

## Run (dev, on the Mac)

No hardware needed — `app/motor.py` auto-detects the missing `RPi.GPIO` and
runs in stub mode (logs PWM values instead of driving pins). Camera comes
from the Mac's built-in webcam.

```bash
conda activate cv
cd trobot
python main.py
```

Open `http://localhost:8000` in the browser.

First run downloads `yolov8n.pt` automatically (needs internet once).

## Run (on the Pi4)

```bash
pip install -r requirements.txt   # adds RPi.GPIO on top of the same stack
python main.py
```

Open the Pi's address from the Mac browser — either `http://<pi-lan-ip>:8000`
on the same WiFi, or `http://<pi-netbird-ip>:8000` once Netbird is connected
(see project notes on remote/off-LAN control).

## Known simplifications

- Auto-follow steering is a plain P-controller (`app/config.py`:
  `AUTO_KP_TURN`/`AUTO_KP_FWD`/`AUTO_TARGET_AREA`) — no smoothing/PID. Tune
  those constants if it oscillates.
- Gamepad axis indices in `app/static/index.html` (`AXIS_X`/`AXIS_Y`) are a
  guess — check `navigator.getGamepads()[0].axes` in the browser console
  with the flyjoy joystick plugged into the Mac and adjust to match.
- No status broadcast back to the browser yet (mode indicator is client-side
  optimistic only) — add a periodic WS push from the server if that drifts
  in practice.
- YOLOv8n on Pi4 CPU (no Coral/Hailo accelerator) — expect ~5-15 FPS as-is.
