"""Differential-drive motor control over 2x BTS7960 via GPIO PWM (gpiozero).

R_EN/L_EN on both BTS7960 boards are wired straight to 3.3V (per Bot.pdf),
so software only ever drives RPWM/LPWM -- no enable pin to toggle.

On anything without a working gpiozero pin factory (e.g. a Mac with no GPIO
hardware), this runs in STUB mode: same interface, just logs the duty cycle
it *would* send. Lets the rest of the app (web UI, vision, arbiter) be
developed and tested off-Pi before ever touching real hardware.
"""
import logging

from . import config

log = logging.getLogger("trobot.motor")

try:
    from gpiozero import PWMOutputDevice
    # A bare import always succeeds even with zero GPIO hardware -- creating
    # a real device is what actually triggers gpiozero's pin-factory
    # detection (lgpio / RPi.GPIO / pigpio), so probe with a throwaway one.
    _probe = PWMOutputDevice(config.LEFT_RPWM, frequency=config.PWM_FREQ_HZ)
    _probe.close()
    _HAS_GPIO = True
except Exception:
    _HAS_GPIO = False
    log.warning("gpiozero has no working GPIO backend -> motor driver running in STUB mode (no hardware)")


class _PWMPair:
    """One BTS7960 channel: RPWM drives forward, LPWM drives reverse."""

    def __init__(self, rpwm_pin: int, lpwm_pin: int):
        self.rpwm_pin = rpwm_pin
        self.lpwm_pin = lpwm_pin
        if _HAS_GPIO:
            self._rpwm = PWMOutputDevice(rpwm_pin, frequency=config.PWM_FREQ_HZ)
            self._lpwm = PWMOutputDevice(lpwm_pin, frequency=config.PWM_FREQ_HZ)

    def set_speed(self, speed: float):
        """speed in -1..1, positive = forward."""
        speed = max(-1.0, min(1.0, speed))
        duty = abs(speed)
        if not _HAS_GPIO:
            direction = "FWD" if speed >= 0 else "REV"
            log.debug("pins(%s,%s) %s duty=%.0f%%", self.rpwm_pin, self.lpwm_pin, direction, duty * 100)
            return
        if speed >= 0:
            self._rpwm.value = duty
            self._lpwm.value = 0
        else:
            self._rpwm.value = 0
            self._lpwm.value = duty

    def stop(self):
        self.set_speed(0.0)

    def close(self):
        if _HAS_GPIO:
            self._rpwm.close()
            self._lpwm.close()


class MotorDriver:
    """Differential drive: vx=forward/back, vz=turn, both -1..1."""

    def __init__(self):
        self.left = _PWMPair(config.LEFT_RPWM, config.LEFT_LPWM)
        self.right = _PWMPair(config.RIGHT_RPWM, config.RIGHT_LPWM)

    def drive(self, vx: float, vz: float):
        left_speed = vx - vz
        right_speed = vx + vz
        norm = max(1.0, abs(left_speed), abs(right_speed))  # avoid clipping distortion
        self.left.set_speed(left_speed / norm)
        self.right.set_speed(right_speed / norm)

    def stop(self):
        self.left.stop()
        self.right.stop()

    def cleanup(self):
        self.stop()
        self.left.close()
        self.right.close()
