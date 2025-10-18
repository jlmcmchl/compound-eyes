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
from .node import Graph, FpsNode, DetectCharucoNode, SelectSink, SelectSource
from .node.focus import FocusNode
from .node.stream import DebugNode
from .calibration_routine import CalibrationRoutine, CalibrationConfig


class Camera:
    def __init__(self, device: Device, parent: NetworkTable, debug_port: int):
        self.device = device

        self.nt_table = parent.getSubTable(self.device.info.bus_info)
        role_topic = self.nt_table.getStringTopic("role")
        self.role_entry = role_topic.getEntry("Change Me!")
        self.mode_entry = NetworkChooser(
            self.nt_table, "mode", ["setup", "focus", "calibration"], "setup"
        )

        self.config_table = CameraControlsTable(
            self.device, self.nt_table.getSubTable("config")
        )

        self.edges: list[Queue[Capture]] = [
            Queue(maxsize=1),
            Queue(maxsize=1),
            Queue(maxsize=1),
            Queue(maxsize=1),
            Queue(maxsize=1),
            Queue(maxsize=1),
            Queue(maxsize=1),
            Queue(maxsize=1),
            Queue(maxsize=1),
            Queue(maxsize=1),
        ]

        self.nodes = [
            SelectSink(
                self.edges[0],
                {
                    "setup": self.edges[1],
                    "focus": self.edges[2],
                    "calibration": self.edges[3],
                },
                self.mode_entry.get,
            ),
            FpsNode(self.edges[1], self.edges[4], "source"),
            FocusNode(self.edges[2], self.edges[5], self.device.info.bus_info),
            DetectCharucoNode(self.edges[3], self.edges[6], self.device.info.bus_info),
            FpsNode(self.edges[5], self.edges[7], "focus"),
            FpsNode(self.edges[6], self.edges[8], "calibration"),
            SelectSource(
                {
                    "setup": self.edges[4],
                    "focus": self.edges[7],
                    "calibration": self.edges[8],
                },
                self.edges[9],
                self.mode_entry.get,
            ),
            DebugNode(self.device.info.bus_info, debug_port, self.edges[9]),
        ]

        self.calibration_node = self.nodes[3]

        self.graph = Graph(self.device.info.bus_info)

        for node in self.nodes:
            self.graph.add_node(node)

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

                    if not self.edges[0].full():
                        self.edges[0].put(Capture(frame, normalized_frame))

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

        # Assigned in load_cameras()
        self.cameras: dict[Path, Camera | None] = {}

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
