"""
Deep-sleep / retry planning — pure decision logic for the ESP32 firmware.

Phase 2 lets the device deep-sleep between uses and wake on a button press
(microamp standby). The wrinkle vs. the Pi: a deep-sleeping ESP32 can't run a
background retry thread, so buffered thoughts upload either (a) on the next
button-press wake, or (b) via a periodic timer wake if the user opts in
(promptness vs. battery). These helpers make the decisions; main.py applies them
with machine.deepsleep / esp32.wake_on_ext0.
"""


def should_enter_sleep(idle_elapsed_s, idle_timeout_s):
    """True once idle at least ``idle_timeout_s``. A timeout <= 0 disables sleep
    (the device stays always-on — the Phase 1 default until sleep is verified)."""
    if idle_timeout_s <= 0:
        return False
    return idle_elapsed_s >= idle_timeout_s


def sleep_duration_ms(has_backlog, timer_wake_enabled, retry_interval_s):
    """Deep-sleep duration in ms, or ``None`` meaning 'sleep until a button press'.

    - No backlog, or timer-wake disabled -> ``None`` (button-only wake; best battery).
    - Backlog present and timer-wake enabled -> wake after ``retry_interval_s`` to
      retry the backlog, then re-evaluate.
    """
    if has_backlog and timer_wake_enabled and retry_interval_s > 0:
        return int(retry_interval_s * 1000)
    return None
