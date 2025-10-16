from linuxpy.video.device import Frame
from dataclasses import dataclass, field
import numpy as np
from typing import Any


@dataclass
class Capture:
    frame: Frame
    image: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)

    def copy(self):
        # Only clone the things that are written to by the application
        return Capture(self.frame, self.image.copy(), self.metadata.copy())
