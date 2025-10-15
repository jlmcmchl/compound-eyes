from linuxpy.video.device import Device, iter_video_capture_files
from ntcore import NetworkTable
from pathlib import Path
import logging

from camera_controls_nt import CameraControlsTable
from debug_server import VideoQueueConsumer
from queue import Queue
import threading

from convert_frame import process_frame
from network_choice import NetworkChooser
from fps_counter import FpsCounter
from datatypes import Capture
import traceback


class Camera:
    def __init__(self, device: Device, parent: NetworkTable, debug_port: int):
        self.device = device

        self.raw_queue: Queue[Capture] = Queue(maxsize=1)
        self.debug_server = VideoQueueConsumer(debug_port, self.raw_queue)

        self.nt_table = parent.getSubTable(self.device.info.bus_info)
        role_topic = self.nt_table.getStringTopic("role")
        self.role_entry = role_topic.getEntry("Change Me!")
        self.mode_entry = NetworkChooser(
            self.nt_table, "mode", ["setup", "calibration", "active"], "setup"
        )

        self.config_table = CameraControlsTable(
            self.device, self.nt_table.getSubTable("config")
        )

        self.main_thread = threading.Thread(name=device, target=self.main_loop)
        self._stop = False

        self.fps_counter = FpsCounter()

    def start(self):
        self.main_thread.start()

    def stop(self):
        self._stop = True
        self.main_thread.join()

    def main_loop(self):
        try:
            self.device.open()

            self.config_table.load_controls()

            while not self._stop:
                self.config_table.update()

                for frame in self.device:
                    normalized_frame = process_frame(frame)
                    fps = self.fps_counter.getfps()

                    self.mode_entry.periodic()
                    mode = self.mode_entry.get()

                    if not self.raw_queue.full():
                        self.raw_queue.put(Capture(frame, fps, normalized_frame))

                    if mode == "setup":
                        if self.config_table.changed():
                            break
                    else:
                        self.config_table.sync()

                    if self._stop:
                        break
        except OSError as e:
            self.device.log.error(f"Something's wrong! {e}")
            traceback.print_exc()
        finally:
            self.device.close()


class CameraManager:
    logger = logging.getLogger("CameraManager")

    def __init__(self, table: NetworkTable):
        self.table = table
        self.debug_port = 5800

        self.streams = table.getStringArrayTopic("video/streams").getEntry([])

        # Assigned in load_cameras()
        self.cameras: dict[Path, Camera] = {}

    def add_mjpg_stream(self, port):
        new_stream = f"mjpeg:http://robojackets-coprocessor.attlocal.net:{port}"
        streams = self.streams.get()

        if new_stream not in streams:
            streams.append(new_stream)
            self.streams.set(streams)

    def remove_mjpg_stream(self, port):
        pass

    def load_cameras(self):
        capture_files = list(iter_video_capture_files())

        new_devices = 0
        for file in capture_files:
            if file not in self.cameras:
                new_devices += 1
                try:
                    self.logger.info(f"Adding {file} to the camera manager.")
                    device = Device(file)
                    device.open()
                    camera = Camera(device, self.table, self.debug_port)
                    camera.start()

                    self.add_mjpg_stream(self.debug_port)

                    self.cameras[file] = camera
                    self.debug_port += 1
                except Exception as e:
                    self.logger.error(
                        f"Cannot monitor {file} due to {e}. Will not try again until it is removed."
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
                camera.stop()

        self.cameras = {}
