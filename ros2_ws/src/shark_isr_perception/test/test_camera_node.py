"""Unit test for the one bit of real logic in camera_node: BGR->RGB channel swap."""

import numpy as np

from shark_isr_perception.camera_node import _bgr_frame_to_rgb_bytes


def test_bgr_to_rgb_swaps_channels() -> None:
    # A 2x2 frame with only the BGR blue channel (index 0) set.
    bgr = np.zeros((2, 2, 3), dtype=np.uint8)
    bgr[:, :, 0] = 200  # blue in OpenCV's BGR

    rgb = np.frombuffer(_bgr_frame_to_rgb_bytes(bgr), dtype=np.uint8).reshape(2, 2, 3)

    # After swap, blue must land in the rgb8 blue slot (index 2), red slot empty.
    assert (rgb[:, :, 2] == 200).all()
    assert (rgb[:, :, 0] == 0).all()
    assert rgb.tobytes() == _bgr_frame_to_rgb_bytes(bgr)  # length/contiguity sane
