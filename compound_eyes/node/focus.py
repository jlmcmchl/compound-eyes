from . import Node
from queue import Queue, Empty

import cv2
from ..datatypes import Capture
import numpy
from scipy.ndimage import convolve


def modified_laplacian(frame):
    frame = frame / 255
    M = numpy.array([[0, 0, 0], [-1, 2, -1], [0, 0, 0]])
    Lx = convolve(frame, M, mode="nearest")
    Ly = convolve(frame, M.T, mode="nearest")
    Lx = numpy.clip(Lx, a_min=0, a_max=65535)
    Ly = numpy.clip(Ly, a_min=0, a_max=65535)
    FM = numpy.abs(Lx) + numpy.abs(Ly)
    return FM.mean()


class FocusNode(Node):
    def __init__(self, source: Queue[Capture], sink: Queue, name: str):
        self.source = source
        self.sink = sink

        self.history: list[tuple[float, float]] = []
        self.history_length = 10
        self.roi = (0.5, 0.5)

        super().__init__(name)

    def measure(self, timestamp: float, frame: cv2.typing.MatLike):
        roi_width = int(frame.shape[1] * self.roi[1])
        roi_height = int(frame.shape[0] * self.roi[0])
        roi_x = (frame.shape[1] - roi_width) // 2
        roi_y = (frame.shape[0] - roi_height) // 2

        roi = frame[roi_y : roi_y + roi_height, roi_x : roi_x + roi_width]

        focus_metric = modified_laplacian(roi)

        self.history.append((timestamp, focus_metric))

        while (
            len(self.history) != 0
            and self.history_length < timestamp - self.history[0][0]
        ):
            self.history.pop(0)

        return focus_metric / max(self.history, key=lambda x: x[1])[1]

    def paint(self, frame: cv2.typing.MatLike):
        graph_height = frame.shape[0] // 2
        graph_width = frame.shape[1] // 2

        graph_y = frame.shape[0]
        graph_x = 0

        first_time = self.history[0][0]

        latest_time = self.history[-1][0]

        roi_width = int(frame.shape[1] * self.roi[1])
        roi_height = int(frame.shape[0] * self.roi[0])
        roi_x = (frame.shape[1] - roi_width) // 2
        roi_y = (frame.shape[0] - roi_height) // 2
        roi_min = (roi_x, roi_y)
        roi_max = (roi_x + roi_width, roi_y + roi_height)

        max_focus_metric = max(self.history, key=lambda entry: entry[1])[1]

        def scale(value, min_value, max_value, scaled_max, offset):
            if max_value == 0:
                return offset

            return int(
                ((value - min_value) / (max_value - min_value)) * scaled_max + offset
            )

        # draw the ROI rectangle on the frame
        cv2.rectangle(frame, roi_min, roi_max, (0, 255, 255), 2)

        # draw maximum line for the graph
        cv2.line(
            frame,
            (graph_x, graph_y - graph_height),
            (graph_x + graph_width, graph_y - graph_height),
            (0x80, 0x80, 0),
            2,
        )

        # draw focus graph proper
        for i in range(1, len(self.history)):
            last_value = self.history[i - 1]
            last_time = last_value[0]
            last_focus = last_value[1]

            current_value = self.history[i]
            current_time = current_value[0]
            current_focus = current_value[1]

            cv2.line(
                frame,
                (
                    scale(last_time, first_time, latest_time, graph_width, graph_x),
                    scale(last_focus, 0, max_focus_metric, -graph_height, graph_y),
                ),
                (
                    scale(current_time, first_time, latest_time, graph_width, graph_x),
                    scale(current_focus, 0, max_focus_metric, -graph_height, graph_y),
                ),
                (0, 255, 0),
                2,
            )

    def loop(self):
        try:
            capture = self.source.get(timeout=0.1)

            greyscale = cv2.cvtColor(capture.image, cv2.COLOR_BGR2GRAY)

            percent_focus = self.measure(capture.frame.timestamp, greyscale)

            self.paint(capture.image)

            capture.metadata["percent_focus"] = percent_focus

            if not self.sink.full():
                self.sink.put(capture)

        except Empty:
            pass
