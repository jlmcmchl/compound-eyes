import time
import logging
from ntcore import NetworkTableInstance
from compound_eyes.camera_manager import CameraManager
import socket


def main():
    nt = NetworkTableInstance.getDefault()
    nt.startClient4(f"{socket.gethostname()}-compoundeyes")
    nt.setServer("localhost")

    camera_manager = CameraManager(nt.getTable("cameras"))

    try:
        while True:
            camera_manager.load_cameras()

            time.sleep(0.1)

    finally:
        camera_manager.unload_cameras()
        nt.stopServer()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    main()
