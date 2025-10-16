import cv2
import numpy as np
from dataclasses import dataclass
from cv2 import aruco
from .datatypes import Capture
import heapq
import os
from pathlib import Path
import shutil
import math
import subprocess
import multiprocessing as mp
from mrcal.cameramodel import cameramodel


@dataclass
class CalibrationConfig:
    aruco_dict: str
    board_size: tuple[int, int]
    square_size: float
    marker_size: float
    capture_max: int
    image_size: tuple[int, int]
    fov: float
    lens_model: str
    device_name: str

    def getDetector(self) -> cv2.aruco.CharucoDetector:
        assert self.aruco_dict in dir(aruco)
        aruco_dict = cv2.aruco.getPredefinedDictionary(eval(f"aruco.{self.aruco_dict}"))
        charuco_board = cv2.aruco.CharucoBoard(
            self.board_size,
            self.square_size,
            self.marker_size,
            aruco_dict,
        )
        charuco_params = cv2.aruco.CharucoParameters()
        charuco_params.tryRefineMarkers = True
        detector_params = cv2.aruco.DetectorParameters()
        # parameters pulled from PhotonVision
        detector_params.adaptiveThreshWinSizeMin = 11
        detector_params.adaptiveThreshWinSizeStep = 40
        detector_params.adaptiveThreshWinSizeMax = 91
        detector_params.adaptiveThreshConstant = 10
        detector_params.errorCorrectionRate = 0
        detector_params.useAruco3Detection = False
        detector_params.minMarkerLengthRatioOriginalImg = 0.02
        detector_params.minSideLengthCanonicalImg = 32
        refine_params = cv2.aruco.RefineParameters()
        return cv2.aruco.CharucoDetector(
            charuco_board, charuco_params, detector_params, refine_params
        )


def estimate_focal_length(fov, width, height):
    def calculateHorizontalVerticalFoV(fov, width, height):
        diagfov = math.radians(fov)
        diagAspect = math.hypot(width, height)

        hview = math.atan(math.tan(diagfov / 2) * (width / diagAspect)) * 2
        vview = math.atan(math.tan(diagfov / 2) * (height / diagAspect)) * 2

        return (math.degrees(hview), math.degrees(vview))

    views = calculateHorizontalVerticalFoV(fov, width, height)
    hfov = math.radians(views[0])
    vfov = math.radians(views[1])

    hfl = width / 2 / math.tan(hfov / 2)
    vfl = height / 2 / math.tan(vfov / 2)

    return (hfl, vfl)


class CalibrationRoutine:
    def __init__(self, config: CalibrationConfig):
        self.config = config
        self.detector = config.getDetector()
        self.dirpath: Path | None = None

        self.corner_cache: list[tuple[int, Path, np.ndarray, np.ndarray]] = []
        self.capture_count = 0

    def run(self, capture: Capture):
        (
            chessboard_corner_coords,
            chessboard_corner_ids,
            marker_corner_coords,
            marker_ids,
        ) = self.detector.detectBoard(capture.image)

        if chessboard_corner_coords is not None:
            self.add_capture_to_calibration(
                capture, chessboard_corner_ids, chessboard_corner_coords
            )

            capture.metadata["corners_found"] = chessboard_corner_ids.shape[0]
        else:
            capture.metadata["corners_found"] = 0

        capture.metadata["total_corners_found"] = sum(
            count for (count, _, _, _) in self.corner_cache
        )

        for val, _, _, corners in self.corner_cache:
            cv2.aruco.drawDetectedCornersCharuco(capture.image, corners)

        if marker_corner_coords is not None:
            cv2.aruco.drawDetectedMarkers(capture.image, marker_corner_coords)

    def add_capture_to_calibration(
        self, capture: Capture, ids: np.ndarray, corners: np.ndarray
    ):
        self.capture_count += 1
        filename = self.save_calibration_image(capture)

        # Only keep the 'best' captures, using corner count as a proxy
        if len(self.corner_cache) == self.config.capture_max:
            (corner_count, fname, _, _) = heapq.heappushpop(
                self.corner_cache, (ids.shape[0], filename, ids, corners)
            )
            print(corner_count, filename)

            os.remove(fname)
        else:
            heapq.heappush(self.corner_cache, (ids.shape[0], filename, ids, corners))

    def save_calibration_image(self, capture: Capture) -> Path:
        if self.dirpath is None:
            raise Exception(
                "Calling this function without calling CalibrationRoutine::begin() is an error!"
            )

        filename = f"img{self.capture_count}.png"

        cv2.imwrite(str(self.dirpath / filename), capture.image)

        return self.dirpath / filename

    def begin(self):
        self.dirpath = (
            Path("calibration")
            / self.config.device_name
            / f"{self.config.image_size[0]}x{self.config.image_size[1]}"
        )

        # clear the target directory
        shutil.rmtree(self.dirpath, ignore_errors=True)
        # recreate it
        self.dirpath.mkdir(parents=True)

    def finish(self):
        # Base case: calibration has not begun
        if self.dirpath is None:
            return
        
        if len(self.corner_cache) == 0:
            return

        if not (self.dirpath / "corners.vnl").exists():
            # step 1: write all corners to corners.vnl
            with open(self.dirpath / "corners.vnl", "w") as f:
                f.write("# filename x y level\n")

                for _, path, ids, corners in self.corner_cache:
                    # Step 1.1: fill out all the missing corners
                    corners_on_board = (self.config.board_size[0] - 1) * (
                        self.config.board_size[1] - 1
                    )
                    corners_to_write = np.full((corners_on_board, 2), -1)

                    for id, corner in zip(ids, corners):
                        corners_to_write[id, :] = corner

                    # Step 1.2: write all corners to the file
                    for corner in corners_to_write:
                        if corner[0] == -1 and corner[1] == -1:
                            f.write(f"{path} - - -\n")
                        else:
                            f.write(f"{path} {corner[0]} {corner[1]} 0\n")

        # step 2: calibrate with mrcal
        self.cli_calibrate()

    def cli_calibrate(self) -> cameramodel:
        if self.dirpath is None:
            raise Exception(
                "Calling this function without calling CalibrationRoutine::begin() is an error!"
            )

        focal_view = estimate_focal_length(
            self.config.fov, self.config.image_size[0], self.config.image_size[1]
        )
        subprocess.run(
            "uv run ./mrcal/mrcal-calibrate-cameras"
            f" --lensmodel {self.config.lens_model}"
            f" --focal {sum(focal_view) / 2}"
            f" --object-width-n {self.config.board_size[0] - 1}"
            f" --object-height-n {self.config.board_size[1] - 1}"
            f" --object-spacing {self.config.square_size}"
            f" --corners-cache {self.dirpath / 'corners.vnl'}"
            f" --jobs {mp.cpu_count()}"
            f" --outdir {self.dirpath}"
            f' "{self.dirpath / "img*.png"}"',
            shell=True,
            check=True,
        )

    def load_calibration(self) -> cameramodel | None:
        if self.dirpath is None:
            raise Exception(
                "Calling this function without calling CalibrationRoutine::begin() is an error!"
            )
        
        if not (self.dirpath / "camera-0.cameramodel").exists():
            return None

        with open(self.dirpath / "camera-0.cameramodel") as f:
            return cameramodel(f)
