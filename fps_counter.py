import time


class FpsCounter:
    def __init__(self):
        self._last_time = None
        self._fps = 0.0

    def getfps(self) -> float:
        now = time.perf_counter()
        if self._last_time is None:
            self._last_time = now
            return 0.0  # Not enough data yet

        dt = now - self._last_time
        self._last_time = now
        if dt <= 0:
            return self._fps
        # Exponential moving average for smoothness
        instant_fps = 1.0 / dt
        alpha = 0.2  # Smoothing parameter (0 = very smooth, 1 = instant)
        self._fps = (1 - alpha) * self._fps + alpha * instant_fps
        return self._fps
