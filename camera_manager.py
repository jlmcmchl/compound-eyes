from linuxpy.video.device import Device, iter_video_capture_files
from ntcore import NetworkTable
from pathlib import Path
import logging

from camera_controls_nt import CameraControlsTable
from debug_server import MjpgStreamer
from queue import Queue
from linuxpy.io import GeventIO
from source import CameraSource


class Camera:
    def __init__(
        self, device: Device, debug_server: MjpgStreamer, parent: NetworkTable
    ):
        self.device = device

        self.nt_table = parent.getSubTable(self.device.info.bus_info)
        role_topic = self.nt_table.getStringTopic("role")
        self.role_entry = role_topic.getEntry("Change Me!")

        queue: Queue = Queue(maxsize=1)
        debug_server.add_stream(self.role_entry.get(), queue)
        self.camera_source = CameraSource(self.device, queue)

        self.config_table = CameraControlsTable(
            self.device, self.nt_table.getSubTable("config"), self.camera_source
        )

    def update_controls(self):
        self.config_table.update()

    def open(self):
        self.device.open()

        if self.config_table:
            self.config_table.load_controls()

    def close(self):
        if self.config_table:
            self.config_table.unload_controls()
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
                    device = Device(file, io=GeventIO)
                    camera = Camera(device, self.debug_server, self.table)

                    camera.open(self.table)
                    camera.update_controls()

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
                camera.close()
            del self.cameras[file]

    def unload_cameras(self):
        for camera in self.cameras.values():
            if camera is not None:
                camera.close()

        self.cameras = {}

    def update_controls(self):
        for camera in self.cameras.values():
            camera.update_controls()
