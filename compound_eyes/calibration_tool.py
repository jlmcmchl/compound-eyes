import cv2
import math
import subprocess
import multiprocessing as mp

from mrcal.cameramodel import cameramodel
import glob


def get_image_corners(args):
    (board_width, board_height, square_size, marker_size, path) = args
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
    charuco_board = cv2.aruco.CharucoBoard(
        (board_width, board_height),
        square_size,
        marker_size,
        aruco_dict,
    )
    charuco_params = cv2.aruco.CharucoParameters()
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
    detector = cv2.aruco.CharucoDetector(
        charuco_board, charuco_params, detector_params, refine_params
    )

    corner_count = (board_width - 1) * (board_height - 1)

    image = cv2.imread(path)

    corners = [None] * corner_count

    if image is None:
        print(f"could not load {path}")
    else:
        (
            chessboard_corner_coords,
            chessboard_corner_ids,
            marker_corner_coords,
            marker_ids,
        ) = detector.detectBoard(image)

        if chessboard_corner_ids is not None:
            for i in range(len(chessboard_corner_ids)):
                corner_id = chessboard_corner_ids[i][0]
                corner_coord = chessboard_corner_coords[i][0]
                corners[corner_id] = corner_coord

    return (path, corners)


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


class CalibrationTool:
    def __init__(
        self,
        fov: float,
        board_size: tuple[float, float],
        image_size: tuple[float, float],
        square_size: float,
        marker_size: float,
        image_folder: str,
        tag_family: str = "DICT_4X4_1000",
        lens_model: str = "LENSMODEL_OPENCV8",
    ):
        self.fov = fov
        self.board_size = board_size
        self.image_size = image_size
        self.square_size = square_size
        self.marker_size = marker_size

        self.tag_family = tag_family
        self.lens_model = lens_model

        self.image_folder = image_folder
        self.image_pattern = f"{self.image_folder}/img*.png"
        self.corners_file = f"{self.image_folder}/corners.vnl"

    def detectCorners(self):
        with mp.Pool() as p:
            corner_detection_results = {
                path: corners
                for path, corners in p.map(
                    get_image_corners,
                    (
                        (
                            self.board_size[0],
                            self.board_size[1],
                            self.square_size,
                            self.marker_size,
                            file,
                        )
                        for file in glob.iglob(self.image_pattern)
                    ),
                )
            }

        with open(self.corners_file, "w") as f:
            f.write("# filename x y level\n")

            for path in corner_detection_results:
                for corner in corner_detection_results[path]:
                    if corner is None:
                        f.write(f"{path} - - -\n")
                    else:
                        f.write(f"{path} {corner[0]} {corner[1]} 0\n")

    def cli_calibrate(self):
        focal_view = estimate_focal_length(
            self.fov, self.image_size[0], self.image_size[1]
        )
        subprocess.run(
            "uv run ./mrcal/mrcal-calibrate-cameras"
            f" --lensmodel {self.lens_model}"
            f" --focal {sum(focal_view) / 2}"
            f" --object-width-n {self.board_size[0] - 1}"
            f" --object-height-n {self.board_size[1] - 1}"
            f" --object-spacing {self.square_size}"
            f" --corners-cache {self.corners_file}"
            f" --jobs {mp.cpu_count()}"
            f" --outdir {self.image_folder}"
            f' "{self.image_pattern}"',
            shell=True,
            check=True,
        )

        return self.load_calibration()

    def load_calibration(self):
        with open(f"{self.image_folder}/camera-0.cameramodel") as f:
            return cameramodel(f)


def main():
    tool = CalibrationTool(
        fov=55,
        board_size=(15, 15),
        image_size=(1600, 1304),
        square_size=0.03,
        marker_size=0.022,
        image_folder="./calibration/1600x1304",
    )

    model = None

    try:
        model = tool.load_calibration()
    except FileNotFoundError:
        pass

    if model is None:
        tool.detectCorners()

        model = tool.cli_calibrate()

    print(model.intrinsics())


if __name__ == "__main__":
    main()
