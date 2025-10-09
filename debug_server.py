from mjpeg_streamer import Stream, MjpegServer
from linuxpy.video.device import Frame
from convert_frame import process_frame
import logging
import threading
from queue import Queue
import cv2
import time
import numpy as np


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


class MjpgTask:
    def __init__(self, queue: Queue, stream: Stream):
        self.queue = queue
        self.stream = stream
        self.counter = FpsCounter()

    def paint(self, image: np.ndarray, fps: float, timestamp: float):
        cv2.putText(
            image,
            f"Fps: {fps:.2f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
            2,
        )

        cv2.putText(
            image,
            f"Timestamp: {timestamp:.2f}",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
            2,
        )

    def submit_frame(self, frame: Frame):
        out = process_frame(frame)
        self.paint(out, self.counter.getfps(), frame.timestamp)
        self.stream.set_frame(out)

    def run(self):
        while True:
            frame = self.queue.get(block=True)

            self.submit_frame(frame)

    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def stop(self):
        self.queue.all_tasks_done()


class MjpgStreamer:
    logger = logging.getLogger("MjpgStreamer")

    def __init__(self):
        self.server = MjpegServer(host="0.0.0.0", port=5800)
        self.tasks = {}
        self.streams = {}

    def restart(self):
        self.server.stop()
        for _, stream in self.streams.items():
            self.server.add_stream(stream)

        self.server.start()

    def add_stream(self, role: str, queue: Queue):
        self.logger.info(f"Adding Stream {role}")
        stream = Stream(role)

        self.streams[role] = stream

        self.tasks[role] = MjpgTask(queue, stream)
        self.tasks[role].start()

        self.restart()
