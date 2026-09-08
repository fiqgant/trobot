"""Control loop: reads SharedState at a fixed rate, drives the motors.
Both failsafe timeouts (link loss, target lost) are enforced inside
state.get_drive_target(), so this loop stays a dumb, fast poller.
"""
import logging
import threading
import time

from . import config
from .motor import MotorDriver

log = logging.getLogger("trobot.control")


def run(state, stop_event: threading.Event):
    motor = MotorDriver()
    period = 1.0 / config.CONTROL_HZ
    try:
        while not stop_event.is_set():
            vx, vz = state.get_drive_target(config.CMD_TIMEOUT, config.AUTO_TIMEOUT)
            motor.drive(vx, vz)
            time.sleep(period)
    finally:
        motor.cleanup()
        log.info("control loop stopped, motors cleaned up")
