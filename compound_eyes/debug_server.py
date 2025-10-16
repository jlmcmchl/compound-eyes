from queue import Queue, Empty
from mjpeg_streamer.server import Server
from mjpeg_streamer.stream import Stream

import threading
import numpy as np
import cv2
import ntcore
import socket

from .datatypes import Capture
from .camera_server import PublishedCameraStream


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

    def __init__(self, name: str, port: int, frame_queue: Queue[Capture]):
        self.frame_queue = frame_queue

        self.stream = Stream("name", fps=30)
        self.server = Server(self.stream, "0.0.0.0", port)

        self.registered_stream = PublishedCameraStream(
            ntcore.NetworkTableInstance.getDefault(), name
        )

        self.server.start()

        self.registered_stream.enable(
            "",
            "1600x1304 MJPG 30 fps",
            [f"mjpg:http://{socket.gethostname()}.attlocal.net:{port}/stream.mjpg"],
        )

        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while True:
            if self._stop:
                break

            try:
                capture = self.frame_queue.get(timeout=0.1)

                paint_frame(capture.image, capture.fps, capture.frame.timestamp)

                self.stream.set_frame(capture.image)

            except Empty:
                pass

    def stop(self):
        self._stop = True
        self.registered_stream.disable()
        self.thread.join()
