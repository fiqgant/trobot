// ---- clock ----
function pad(n) { return String(n).padStart(2, "0"); }
function tickClock() {
  const d = new Date();
  document.getElementById("clockTag").textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
setInterval(tickClock, 1000);
tickClock();
document.getElementById("segHostTop").textContent = location.hostname || "local";
document.getElementById("segHostBot").textContent = location.hostname || "local";

// ---- approx location (IP-based, ground control machine -- NOT robot GPS) ----
// The map image itself is fetched through our own /api/map proxy so the
// Geoapify API key never has to live in this browser-side file.
fetch("https://ipapi.co/json/")
  .then(r => r.json())
  .then(data => {
    const lat = data.latitude, lon = data.longitude;
    if (lat == null || lon == null) throw new Error("no coords");
    document.getElementById("mapImg").src = `/api/map?lat=${lat}&lon=${lon}`;
    document.getElementById("mapLabel").textContent =
      `${data.city || "?"}, ${data.country_name || "?"} (${lat.toFixed(2)}, ${lon.toFixed(2)})`;
  })
  .catch(() => { document.getElementById("mapLabel").textContent = "LOCATION UNAVAILABLE"; });

// ---- WebSocket + link status ----
// `ws` is reassigned on reconnect, so every send goes through wsSend() which
// re-checks readyState each time -- a raw ws.send() throws (and silently
// aborts whatever click handler called it) whenever the link is down.
let ws;

function setLink(ok) {
  const pct = ok ? "97.6%" : "0.0%";
  const txt = ok ? "OK" : "LOST";
  document.getElementById("segLinkTop").textContent = pct;
  document.getElementById("segLinkBot").textContent = pct;
  document.getElementById("segLinkTxtTop").textContent = txt;
  document.getElementById("segLinkTxtBot").textContent = txt;
  document.getElementById("segCoreTop").textContent = ok ? "99.9%" : "0.0%";
  document.getElementById("segCoreBot").textContent = ok ? "99.9%" : "0.0%";
  document.getElementById("statusTag").textContent = ok ? "ONLINE" : "LINK LOST";
}

function wsSend(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

function connectWS() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.addEventListener("open", () => setLink(true));
  ws.addEventListener("close", () => { setLink(false); setTimeout(connectWS, 1000); });
  ws.addEventListener("error", () => setLink(false));
}
connectWS();

function sendCmd(vx, vz) {
  wsSend({ type: "cmd", vx, vz });
  setBars(vx, vz);
}

function setMode(mode, lockLabel) {
  const isAuto = mode === "auto";
  const label = isAuto ? "AUTO-FOLLOW" : "MANUAL";
  document.getElementById("tMode").textContent = label;
  document.getElementById("tMode").className = "val" + (isAuto ? " danger" : "");
  document.getElementById("segModeTop").textContent = label;
  document.getElementById("segModeBot").textContent = label;
  document.getElementById("tLock").textContent = lockLabel !== undefined ? lockLabel : (isAuto ? "PENDING" : "--");
}

function setBars(vx, vz) {
  const barVx = document.getElementById("barVx");
  const barVz = document.getElementById("barVz");
  const place = (el, v) => {
    v = Math.max(-1, Math.min(1, v));
    if (v >= 0) { el.style.left = "50%"; el.style.width = (v * 50) + "%"; }
    else { el.style.left = (50 + v * 50) + "%"; el.style.width = (-v * 50) + "%"; }
  };
  place(barVx, vx);
  place(barVz, vz);
}
setBars(0, 0);

// ---- click-to-lock on the stream ----
// #stream uses object-fit:cover, so it can be cropped relative to the raw
// camera frame -- map the click through the actual displayed sub-rect
// instead of the naive element rect, or the lock point drifts off-target.
const streamEl = document.getElementById("stream");
streamEl.addEventListener("click", (e) => {
  const rect = streamEl.getBoundingClientRect();
  const naturalW = streamEl.naturalWidth || rect.width;
  const naturalH = streamEl.naturalHeight || rect.height;
  const scale = Math.max(rect.width / naturalW, rect.height / naturalH);
  const displayedW = naturalW * scale;
  const displayedH = naturalH * scale;
  const offsetX = (displayedW - rect.width) / 2;
  const offsetY = (displayedH - rect.height) / 2;
  const x = ((e.clientX - rect.left) + offsetX) / displayedW;
  const y = ((e.clientY - rect.top) + offsetY) / displayedH;
  wsSend({ type: "click", x, y });
  setMode("auto", "PENDING");
});

document.getElementById("stopAuto").addEventListener("click", () => {
  wsSend({ type: "mode", value: "manual" });
  setMode("manual");
});

// ---- camera on/off ----
let cameraOn = true;
const camBtn = document.getElementById("toggleCamera");
camBtn.addEventListener("click", () => {
  cameraOn = !cameraOn;
  wsSend({ type: "camera", value: cameraOn ? "on" : "off" });
  camBtn.textContent = "\u{1F4F7} CAMERA: " + (cameraOn ? "ON" : "OFF");
  camBtn.classList.toggle("off", !cameraOn);
  document.getElementById("segCamTop").textContent = cameraOn ? "ON" : "OFF";
  document.getElementById("segCamBot").textContent = cameraOn ? "ON" : "OFF";
  if (!cameraOn) setMode("manual");
});

// ---- object detection on/off (camera keeps streaming raw, no YOLO cost) ----
let detectionOn = true;
const detBtn = document.getElementById("toggleDetection");
detBtn.addEventListener("click", () => {
  detectionOn = !detectionOn;
  wsSend({ type: "detection", value: detectionOn ? "on" : "off" });
  detBtn.textContent = "\u{1F3AF} DETECTION: " + (detectionOn ? "ON" : "OFF");
  detBtn.classList.toggle("off", !detectionOn);
  if (!detectionOn) setMode("manual");
});

// ---- FPS counter (best-effort: relies on the browser firing `load` per MJPEG part) ----
let fpsCount = 0;
streamEl.addEventListener("load", () => { fpsCount++; });
setInterval(() => {
  const v = fpsCount || "--";
  document.getElementById("segFpsTop").textContent = v;
  document.getElementById("segFpsBot").textContent = v;
  fpsCount = 0;
}, 1000);

// ---- virtual joystick (drag the knob) ----
const stick = document.getElementById("stick");
const knob = document.getElementById("knob");
const RADIUS = 42;
let dragging = false;

function setKnob(nx, nz) {
  knob.style.left = 42 + nx * RADIUS + "px";
  knob.style.top = 42 - nz * RADIUS + "px";
}

function handleDrag(clientX, clientY) {
  const rect = stick.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  let dx = (clientX - cx) / (rect.width / 2);
  let dy = (clientY - cy) / (rect.height / 2);
  const mag = Math.hypot(dx, dy);
  if (mag > 1) { dx /= mag; dy /= mag; }
  const vz = dx;
  const vx = -dy;
  setKnob(vz, vx);
  sendCmd(vx, vz);
  setMode("manual");
}

stick.addEventListener("pointerdown", (e) => { dragging = true; handleDrag(e.clientX, e.clientY); });
window.addEventListener("pointermove", (e) => { if (dragging) handleDrag(e.clientX, e.clientY); });
window.addEventListener("pointerup", () => {
  if (!dragging) return;
  dragging = false;
  setKnob(0, 0);
  sendCmd(0, 0);
});

// ---- physical joystick via browser Gamepad API ----
// axis indices below are a guess (typical HID layout: X, Y, Rudder, Throttle
// per the flyjoy sketch's Joystick_ constructor order) -- open the browser
// console, check `navigator.getGamepads()[0].axes`, and adjust to match
// flyjoy's actual reported order.
// Roll/pitch tilt (X/Y) steers; the slide-pot Throttle axis sets how fast --
// direction and speed are independent, like a real throttle+steering rig.
const AXIS_X = 0;
const AXIS_Y = 1;
const AXIS_THROTTLE = 3;
const DEADZONE = 0.08;
let lastGpSent = 0;

function pollGamepad() {
  const pads = navigator.getGamepads ? navigator.getGamepads() : [];
  const gp = pads && pads[0];
  document.getElementById("tGamepad").textContent = gp ? gp.id.slice(0, 18).toUpperCase() : "NONE";

  if (gp) {
    let x = gp.axes[AXIS_X] || 0;
    let y = gp.axes[AXIS_Y] || 0;
    if (Math.abs(x) < DEADZONE) x = 0;
    if (Math.abs(y) < DEADZONE) y = 0;

    // Throttle axis is -1..1 across the slider's full travel -> normalize to 0..1 speed.
    const throttleRaw = gp.axes[AXIS_THROTTLE];
    const speed = throttleRaw === undefined ? 1 : (throttleRaw + 1) / 2;

    const now = performance.now();
    if ((x !== 0 || y !== 0) && now - lastGpSent > 50) {
      sendCmd(-y * speed, x * speed);
      setMode("manual");
      lastGpSent = now;
    }
  }
  requestAnimationFrame(pollGamepad);
}
requestAnimationFrame(pollGamepad);
