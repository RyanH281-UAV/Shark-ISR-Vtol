"""Unit test for detector_node.py's parameter-change callback.

Regression test: `ros2 param set` on mock_detection_prob / mock_burst_frames
used to succeed at the parameter-server level while _run_sim_detection kept
using the value cached at __init__ forever — a silent no-op. Found via a SITL
test (T10) whose live `ros2 param set` to mute mock detections had no effect.

Needs rclpy + the built shark_isr_interfaces on the path, so run this via
`colcon test`, not bare pytest.
"""

import pytest
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.parameter import Parameter

from shark_isr_perception.detector_node import DetectorNode


@pytest.fixture
def node():
    rclpy.init()
    n = DetectorNode()
    yield n
    n.destroy_node()
    rclpy.shutdown()


def test_mock_detection_prob_takes_effect_live(node):
    assert node._mock_prob == 0.02  # perception.yaml default
    result = node._on_params_change([Parameter('mock_detection_prob', value=0.0)])
    assert isinstance(result, SetParametersResult) and result.successful
    assert node._mock_prob == 0.0


def test_mock_burst_frames_takes_effect_live(node):
    result = node._on_params_change([Parameter('mock_burst_frames', value=5)])
    assert result.successful
    assert node._mock_burst_frames == 5


def test_unrelated_param_change_is_ignored(node):
    prob_before = node._mock_prob
    result = node._on_params_change([Parameter('confidence_threshold', value=0.9)])
    assert result.successful
    assert node._mock_prob == prob_before  # untouched, not this callback's job
