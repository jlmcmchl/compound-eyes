import numpy as np
import cv2


def paint_frame(image: np.ndarray, fps: float, timestamp: float):
    cv2.putText(
        image,
        f"Fps: {fps:.2f}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 0, 255),
        2,
    )

    cv2.putText(
        image,
        f"Timestamp: {timestamp:.2f}",
        (10, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 0, 255),
        2,
    )
