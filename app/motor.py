"""Differential-drive motor control over 2x BTS7960 via GPIO software PWM.

R_EN/L_EN on both BTS7960 boards are wired straight to 3.3V (per Bot.pdf),
so software only ever drives RPWM/LPWM -- no enable pin to toggle.

On anything that isn't a Raspberry Pi (no RPi.GPIO), this runs in STUB mode:
same interface, just logs the duty cycle it *would* send. Lets the rest of
the app (web UI, vision, arbiter) be developed and tested on a Mac before
ever touching real hardware.
"""
import logging

from . import config

log = logging.getLogger("trobot.motor")

try:
    import RPi.GPIO as GPIO
    _HAS_GPIO = True
except ImportError:
    _HAS_GPIO = False
    log.warning("RPi.GPIO not available -> motor driver running in STUB mode (no hardware)")


class _PWMPair:
    """One BTS7960 channel: RPWM drives forward, LPWM drives reverse."""

    def __init__(self, rpwm_pin: int, lpwm_pin: int):
        self.rpwm_pin = rpwm_pin
        self.lpwm_pin = lpwm_pin
        if _HAS_GPIO:
            GPIO.setup(rpwm_pin, GPIO.OUT)
            GPIO.setup(lpwm_pin, GPIO.OUT)
            self._rpwm = GPIO.PWM(rpwm_pin, config.PWM_FREQ_HZ)
            self._lpwm = GPIO.PWM(lpwm_pin, config.PWM_FREQ_HZ)
            self._rpwm.start(0)
            self._lpwm.start(0)

    def set_speed(self, speed: float):
        """speed in -1..1, positive = forward."""
        speed = max(-1.0, min(1.0, speed))
        duty = abs(speed) * 100
        if not _HAS_GPIO:
            direction = "FWD" if speed >= 0 else "REV"
            log.debug("pins(%s,%s) %s duty=%.0f%%", self.rpwm_pin, self.lpwm_pin, direction, duty)
            return
        if speed >= 0:
            self._rpwm.ChangeDutyCycle(duty)
            self._lpwm.ChangeDutyCycle(0)
        else:
            self._rpwm.ChangeDutyCycle(0)
            self._lpwm.ChangeDutyCycle(duty)

    def stop(self):
        self.set_speed(0.0)


class MotorDriver:
    """Differential drive: vx=forward/back, vz=turn, both -1..1."""

    def __init__(self):
        if _HAS_GPIO:
            GPIO.setmode(GPIO.BCM)
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
        if _HAS_GPIO:
            GPIO.cleanup()
