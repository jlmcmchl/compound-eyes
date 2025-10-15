import threading
from queue import Queue
from mjpeg_streamer.server import Server
from mjpeg_streamer.stream import Stream
from datatypes import Capture
from paint_frame import paint_frame


class VideoQueueConsumer:
    _stop = False

    def __init__(self, port: int, frame_queue: Queue[Capture]):
        self.frame_queue = frame_queue

        self.stream = Stream("debug", fps=30)
        self.server = Server(self.stream, "0.0.0.0", port)

        self.server.start()

        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        while True:
            capture = self.frame_queue.get()

            paint_frame(capture.image, capture.fps, capture.frame.timestamp)

            self.stream.set_frame(capture.image)

    def stop(self):
        self._stop = True
        self.thread.join()
