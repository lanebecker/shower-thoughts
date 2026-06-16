"""
Button press classification — pure core, host-testable.

The press UX (short = start/stop, 3 s long-hold = cancel) is the fiddliest part
of the state machine, so its decision lives here as a pure function of elapsed
hold time. main.py samples the real pin in a loop and feeds this each tick; tests
feed numbers. main.py only calls ``classify`` *during* a hold (released=False)
until it returns 'long', then drains the release — so a hold that reaches the
long threshold is reported as 'long' before the release is ever seen.
"""


def classify(held_s, released, long_press_s=3.0):
    """Classify an in-progress / just-ended press.

    - still held and reached ``long_press_s`` -> ``'long'``
    - released before reaching it             -> ``'short'``
    - otherwise (still held, not yet long)    -> ``None`` (keep waiting)
    """
    if not released and held_s >= long_press_s:
        return "long"
    if released:
        return "short"
    return None
