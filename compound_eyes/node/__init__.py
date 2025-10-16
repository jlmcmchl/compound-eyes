from queue import Queue, Empty

from threading import Thread
from .fps_counter import FpsCounter
from mjpeg_streamer.server import Server
from mjpeg_streamer.stream import Stream
from ..camera_server import PublishedCameraStream
import socket
import cv2
import numpy as np
import logging
from typing import Any


class Node:
    def __init__(self, name=None):
        self.name = name or self.__class__.__name__
        self._stop = False
        self.thread = Thread(name=name, target=self._run)

    def _run(self):
        while True:
            if self._stop:
                break

            self.loop()

    def loop(self):
        pass

    def stop(self):
        self._stop = True
        self.thread.join()


class Graph:
    def __init__(self, name: str):
        self.nodes: list[Node] = []
        self.name = name
        self.logger = logging.getLogger(self.name)

    def add_node(self, node: Node):
        self.nodes.append(node)
        node.thread.start()

    def stop(self):
        for node in self.nodes:
            self.logger.info(f"Stopping {node.name}...")
            node.stop()
            self.logger.info(f"Stopped {node.name}.")


class ForkNode(Node):
    def __init__(self, source: Queue, sink: list[Queue]):
        self.source = source
        self.sink = sink

        super().__init__()

    def loop(self):
        try:
            capture = self.source.get(timeout=0.1)

            for sink in self.sink:
                if not sink.full():
                    sink.put(capture.copy())

        except Empty:
            pass


class FpsNode(Node):
    # Measures the FPS of the last action to occur in the processing graph
    def __init__(self, source: Queue, sink: Queue, name=None):
        self.source = source
        self.sink = sink
        self.fps = FpsCounter()

        super().__init__(f"{name}_fps")

    def loop(self):
        try:
            capture = self.source.get(timeout=0.1)

            capture.metadata[self.name] = self.fps.getfps()

            if not self.sink.full():
                self.sink.put(capture)

        except Empty:
            pass


class DebugNode(Node):
    def __init__(self, name: str, port: int, source: Queue):
        self.source = source

        self.stream = Stream(name, fps=30)
        self.server = Server(self.stream, "0.0.0.0", port)
        self.server.start()

        self.registered_stream = PublishedCameraStream(name)
        self.registered_stream.enable(
            "",
            "1600x1304 MJPG 30 fps",
            [f"mjpg:http://{socket.gethostname()}.attlocal.net:{port}/stream.mjpg"],
        )

        super().__init__(name)

    def loop(self):
        try:
            capture = self.source.get(timeout=0.1)

            self.paint_frame(capture.image, capture.frame.timestamp, capture.metadata)

            self.stream.set_frame(capture.image)

        except Empty:
            pass

    def paint_frame(
        self, image: np.ndarray, timestamp: float, metadata: dict[str, Any]
    ):
        cv2.putText(
            image,
            f"Timestamp: {timestamp:.2f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
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
                (0, 0, 255),
                2,
            )

            height += 30
