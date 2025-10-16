from queue import Queue
from mjpeg_streamer.server import Server
from mjpeg_streamer.stream import Stream

import threading
import numpy as np
import cv2

from .datatypes import Capture

def paint_frame(image: np.ndarray, fps: float, timestamp: float):
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

class VideoQueueConsumer:
    _stop = False

    def __init__(self, port: int, frame_queue: Queue[Capture]):
        self.frame_queue = frame_queue

        self.stream = Stream("debug", fps=30)
        self.server = Server(self.stream, "0.0.0.0", port)

        self.server.start()

        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while True:
            capture = self.frame_queue.get()

            paint_frame(capture.image, capture.fps, capture.frame.timestamp)

            self.stream.set_frame(capture.image)

    def stop(self):
        self._stop = True
        self.thread.join()
