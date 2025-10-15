from linuxpy.video.device import Frame
from dataclasses import dataclass
import numpy as np


@dataclass
class Capture:
    frame: Frame
    fps: float
    image: np.ndarray
