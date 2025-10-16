from linuxpy.video.device import Device, iter_video_capture_files
from ntcore import NetworkTable
from pathlib import Path
from queue import Queue

import logging
import threading
import traceback

from .camera_controls_nt import CameraControlsTable
from .convert_frame import process_frame
from .network_choice import NetworkChooser
from .datatypes import Capture
from .node import Graph, FpsNode, DebugNode, DetectCharucoNode
from .calibration_routine import CalibrationRoutine, CalibrationConfig


class Camera:
    def __init__(self, device: Device, parent: NetworkTable, debug_port: int):
        self.device = device

        self.raw_queue: Queue[Capture] = Queue(maxsize=1)

        charuco_queue = Queue(maxsize=1)

        debug_queue = Queue(maxsize=1)

        self.graph = Graph(self.device.info.bus_info)

        self.calibration_node = DetectCharucoNode(
            self.raw_queue,
            charuco_queue,
            self.device.info.bus_info,
        )
        self.graph.add_node(self.calibration_node)
        self.graph.add_node(FpsNode(charuco_queue, debug_queue, name="source"))
        self.graph.add_node(
            DebugNode(
                name=self.device.info.bus_info, port=debug_port, source=debug_queue
            )
        )

        self.nt_table = parent.getSubTable(self.device.info.bus_info)
        role_topic = self.nt_table.getStringTopic("role")
        self.role_entry = role_topic.getEntry("Change Me!")
        self.mode_entry = NetworkChooser(
            self.nt_table, "mode", ["setup", "calibration", "active"], "setup"
        )

        self.config_table = CameraControlsTable(
            self.device, self.nt_table.getSubTable("config")
        )

        self.main_thread = threading.Thread(
            name=device.filename.name, target=self.main_loop
        )
        self._stop = False

    def start(self):
        self.main_thread.start()

    def stop(self):
        self._stop = True
        self.main_thread.join()
        self.graph.stop()

    def main_loop(self):
        try:
            self.device.open()

            self.config_table.load_controls()

            while not self._stop:
                self.config_table.update()

                for frame in self.device:
                    normalized_frame = process_frame(frame)

                    last_mode = self.mode_entry.get()
                    self.mode_entry.periodic()
                    mode = self.mode_entry.get()

                    if not self.raw_queue.full():
                        self.raw_queue.put(Capture(frame, normalized_frame))

                    if last_mode == "calibration":
                        if mode != last_mode:
                            routine = self.calibration_node.end_calibration()

                            if routine is not None:
                                routine.finish()

                                camera = routine.load_calibration()

                                if camera is not None:
                                    print("calibrated!!!", camera.intrinsics())
                    elif mode == "calibration":
                        routine = CalibrationRoutine(
                            CalibrationConfig(
                                aruco_dict="DICT_4X4_1000",
                                board_size=(15, 15),
                                square_size=0.03,
                                marker_size=0.022,
                                capture_max=1000,
                                image_size=(
                                    normalized_frame.shape[1],
                                    normalized_frame.shape[0],
                                ),
                                fov=55,
                                lens_model="LENSMODEL_OPENCV8",
                                device_name=self.device.info.bus_info,
                            )
                        )

                        routine.begin()

                        self.calibration_node.begin_calibration(routine)

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
        self.debug_port = 5820

        self.streams = table.getStringArrayTopic("video/streams").getEntry([])

        # Assigned in load_cameras()
        self.cameras: dict[Path, Camera | None] = {}

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
        for file, camera in self.cameras.items():
            if camera is not None:
                self.logger.info(f"Waiting on {file}...")
                camera.stop()
                self.logger.info(f"{file} closed...")

        self.cameras = {}
