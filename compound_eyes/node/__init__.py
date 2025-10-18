from queue import Queue, Empty

from threading import Thread
from .fps_counter import FpsCounter
import cv2
import logging
from typing import Callable
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


class SelectSink(Node):
    def __init__(
        self, source: Queue, sink: dict[str, Queue], selector: Callable[[], str]
    ):
        self.source = source
        self.sink = sink
        self.selector = selector

        super().__init__()

    def loop(self):
        try:
            sink = self.sink[self.selector()]
            if sink is None:
                return

            capture = self.source.get(timeout=0.1)

            if not sink.full():
                sink.put(capture)

        except Empty:
            pass


class SelectSource(Node):
    def __init__(
        self, source: dict[str, Queue], sink: Queue, selector: Callable[[], str]
    ):
        self.source = source
        self.sink = sink
        self.selector = selector

        super().__init__()

    def loop(self):
        try:
            source = self.source[self.selector()]
            if source is None:
                return

            capture = source.get(timeout=0.1)

            if not self.sink.full():
                self.sink.put(capture)

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
