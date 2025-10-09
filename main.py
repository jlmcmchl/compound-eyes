import time
import logging
from ntcore import NetworkTableInstance
from camera_manager import CameraManager


def main():
    nt = NetworkTableInstance.getDefault()
    nt.startServer()

    camera_manager = CameraManager(nt.getTable("cameras"))

    try:
        while True:
            camera_manager.load_cameras()
            camera_manager.update_controls()

            time.sleep(0.1)

    finally:
        camera_manager.unload_cameras()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    main()
