from linuxpy.video.device import Frame, PixelFormat
import numpy as np
import cv2


def process_frame(frame_data: Frame) -> np.ndarray:
    """Process raw frame data into OpenCV image"""
    # Convert frame data to numpy array
    frame_array = np.frombuffer(frame_data.data, dtype=np.uint8)

    try:
        current_format = frame_data.format
        pixel_format = current_format.pixel_format
        width = current_format.width
        height = current_format.height

        # Handle different pixel formats
        if pixel_format == PixelFormat.YUYV:
            # YUYV format - 2 bytes per pixel
            # frame might be incomplete - that's why we copy it into a full-size array
            width = current_format.width
            height = current_format.height
            onto = np.zeros(height * width * 2, dtype=frame_array.dtype)
            length = min(frame_array.size, onto.size)
            onto[:length] = frame_array[:length]
            image = onto.reshape((height, width, 2))
            image = cv2.cvtColor(image, cv2.COLOR_YUV2BGR_YUYV)
        elif pixel_format == PixelFormat.MJPEG:
            # JPEG format - decode as JPEG
            image = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Failed to decode JPEG")
        else:
            raise Exception(f"Unknown pixel_format {pixel_format}")

        return image

    except Exception as e:
        print(
            f"Error processing frame: could not decode {frame_data.pixel_format.name} {e}"
        )
        # Return a simple error display
        image = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.putText(
            image,
            "Frame processing error",
            (10, height // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
            2,
        )
        return image
