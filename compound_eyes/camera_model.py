from dataclasses import dataclass
import ast


@dataclass
class CameraModel:
    def __init__(
        self,
        *,
        lensmodel: str,
        intrinsics: list[float],
        valid_intrinsics_region: list[list[int]],
        rt_cam_ref: list[int],
        imagersize: list[int],
        icam_intrinsics: int,
        optimization_inputs: bytes,
    ):
        self.lensmodel = lensmodel
        self.intrinsics = intrinsics
        self.valid_intrinsics_region = valid_intrinsics_region
        self.rt_cam_ref = rt_cam_ref
        self.imagersize = imagersize
        self.icam_intrinsics = icam_intrinsics
        self.optimization_inputs = optimization_inputs


def from_file(content) -> CameraModel:
    data = ast.literal_eval(content)

    return CameraModel(
        lensmodel=data['lensmodel'],
        intrinsics = data['intrinsics'],
        valid_intrinsics_region = data['valid_intrinsics_region'],
        rt_cam_ref = data['rt_cam_ref'],
        imagersize = data['imagersize'],
        icam_intrinsics = data['icam_intrinsics'],
        optimization_inputs = data['optimization_inputs'],
    )