import socket

from . import Node
from queue import Queue, Empty
from mjpeg_streamer.server import Server
from mjpeg_streamer.stream import Stream
from ..camera_server import PublishedCameraStream
from typing import Any
from ..datatypes import Capture
import cv2


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(("10.254.254.254", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        s.close()
    return IP


class DebugNode(Node):
    def __init__(
        self,
        name: str,
        port: int,
        source: Queue[Capture],
    ):
        self.source = source

        self.stream = Stream(name, fps=30)
        self.server = Server(self.stream, "0.0.0.0", port)
        self.server.start()

        self.registered_stream = PublishedCameraStream(name)
        self.registered_stream.enable(
            "",
            "1600x1304 MJPG 30 fps",
            [f"mjpg:http://{get_ip()}:{port}/stream.mjpg"],
        )

        super().__init__(name)

    def loop(self):
        try:
            capture = self.source.get(timeout=0.1)
            image = capture.image.copy()

            self.paint_frame(image, capture.frame.timestamp, capture.metadata)

            self.stream.set_frame(image)

        except Empty:
            pass

    def paint_frame(
        self, image: cv2.typing.MatLike, timestamp: float, metadata: dict[str, Any]
    ):
        cv2.putText(
            image,
            f"Timestamp: {timestamp:.2f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

        height = 60
        for key, value in metadata.items():
            cv2.putText(
                image,
                f"{key}: {value:.2f}",
                (10, height),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )

            height += 30
