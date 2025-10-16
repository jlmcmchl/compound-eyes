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
from dataclasses import dataclass
from cv2 import aruco
from ..datatypes import Capture
from ..calibration_routine import CalibrationRoutine


class Node:
    def __init__(self, name: str | None = None):
        if name is None:
            self.name = self.__class__.__name__
        else:
            self.name = f"{self.__class__.__name__}_{name}"
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

        super().__init__(name)

    def loop(self):
        try:
            capture = self.source.get(timeout=0.1)

            capture.metadata[self.name] = self.fps.getfps()

            if not self.sink.full():
                self.sink.put(capture)

        except Empty:
            pass


@dataclass
class CalibrationConfig:
    aruco_dict: str
    board_size: tuple[int, int]
    square_size: float
    marker_size: float
    capture_max: int
    image_size: tuple[int, int]
    fov: float
    lens_model: str

    def getDetector(self) -> cv2.aruco.CharucoDetector:
        assert self.aruco_dict in dir(aruco)
        aruco_dict = cv2.aruco.getPredefinedDictionary(eval(f"aruco.{self.aruco_dict}"))
        charuco_board = cv2.aruco.CharucoBoard(
            self.board_size,
            self.square_size,
            self.marker_size,
            aruco_dict,
        )
        charuco_params = cv2.aruco.CharucoParameters()
        detector_params = cv2.aruco.DetectorParameters()
        # parameters pulled from PhotonVision
        detector_params.adaptiveThreshWinSizeMin = 11
        detector_params.adaptiveThreshWinSizeStep = 40
        detector_params.adaptiveThreshWinSizeMax = 91
        detector_params.adaptiveThreshConstant = 10
        detector_params.errorCorrectionRate = 0
        detector_params.useAruco3Detection = False
        detector_params.minMarkerLengthRatioOriginalImg = 0.02
        detector_params.minSideLengthCanonicalImg = 32
        refine_params = cv2.aruco.RefineParameters()
        return cv2.aruco.CharucoDetector(
            charuco_board, charuco_params, detector_params, refine_params
        )


class DetectCharucoNode(Node):
    def __init__(self, source: Queue[Capture], sink: Queue, name: str):
        self.source = source
        self.sink = sink
        self.routine: CalibrationRoutine | None = None

        super().__init__(name)

    def loop(self):
        try:
            capture = self.source.get(timeout=0.1)

            if self.routine is not None:
                self.routine.run(capture)

            if not self.sink.full():
                self.sink.put(capture)

        except Empty:
            pass

    def begin_calibration(self, routine: CalibrationRoutine):
        self.routine = routine

    def end_calibration(self) -> CalibrationRoutine | None:
        routine = self.routine
        self.routine = None
        return routine


class DebugNode(Node):
    def __init__(self, name: str, port: int, source: Queue, sink: Queue | None = None):
        self.source = source
        self.sink = sink

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
            image = capture.image.copy()

            self.paint_frame(image, capture.frame.timestamp, capture.metadata)

            self.stream.set_frame(image)

            if self.sink and not self.sink.full():
                self.sink.put(capture)

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
