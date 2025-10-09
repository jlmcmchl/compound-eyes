from linuxpy.video.device import Device
from queue import Queue
import threading
import time


class CameraSource:
    def __init__(self, device: Device, queue: Queue):
        self.device = device
        self.queue = queue
        self._is_running = False

        self.thread = threading.Thread(target=self.stream, daemon=True)
        self.thread.start()

    def start(self):
        self._is_running = True

    def stop(self):
        self._is_running = False

    def stream(self):
        while True:
            while not self._is_running:
                time.sleep(1)

            try:
                for frame in self.device:
                    if not self._is_running:
                        break
                    if not self.queue.full():
                        self.queue.put(frame)
            except AttributeError:
                # this is the error that happens when the device is closed
                pass
