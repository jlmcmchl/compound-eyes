from linuxpy.video.device import Device, iter_video_capture_files
from ntcore import NetworkTable
from pathlib import Path
import logging

from camera_controls_nt import CameraControlsTable
from debug_server import MjpgStreamer
from queue import Queue
import threading

from convert_frame import process_frame


class Camera:
    def __init__(self, device: str, debug_server: MjpgStreamer, parent: NetworkTable):
        self.device = Device(device)
        self.device.open()

        self.nt_table = parent.getSubTable(self.device.info.bus_info)
        role_topic = self.nt_table.getStringTopic("role")
        self.role_entry = role_topic.getEntry("Change Me!")

        self.queue: Queue = Queue(maxsize=1)
        debug_server.add_stream(self.role_entry.get(), self.queue)

        self.config_table = CameraControlsTable(
            self.device, self.nt_table.getSubTable("config"), self.camera_source
        )

        self.main_thread = threading.Thread(name=device, target=self.main_loop)
        self._stop = False

    def start(self):
        self.main_thread.start()

    def stop(self):
        self._stop = True
        self.main_thread.join()

    def main_loop(self):
        try:
            self.config_table.load_controls()

            while not self._stop:
                self.update_controls()

                for frame in self.device:
                    normalized_frame = process_frame(frame)
                    if not self.queue.full():
                        self.queue.put((frame, normalized_frame))

                    if self.config_table.changed():
                        break
        finally:
            self.device.close()


class CameraManager:
    logger = logging.getLogger("CameraManager")

    def __init__(self, table: NetworkTable):
        self.table = table
        self.debug_server = MjpgStreamer()

        # Assigned in load_cameras()
        self.cameras: dict[Path, Camera] = {}

    def load_cameras(self):
        capture_files = list(iter_video_capture_files())

        new_devices = 0
        for file in capture_files:
            if file not in self.cameras:
                new_devices += 1
                try:
                    self.logger.info(f"Adding {file} to the camera manager.")
                    camera = Camera(file, self.debug_server, self.table)
                    camera.start()

                    self.cameras[file] = camera
                except Exception as e:
                    self.logger.error(
                        f"Cannot monitor {file.name} due to {e}. Will not try again until it is removed."
                    )
                    self.cameras[file] = None
                    raise

        if new_devices:
            self.logger.info(f"Found {new_devices} video devices.")

        to_remove = [file for file in self.cameras if file not in capture_files]
        for file in to_remove:
            self.logger.info(f"Removing {file} from the camera manager.")
            camera = self.cameras[file]
            if camera is not None:
                camera.stop()
            del self.cameras[file]

    def unload_cameras(self):
        for camera in self.cameras.values():
            if camera is not None:
                camera.close()

        self.cameras = {}
