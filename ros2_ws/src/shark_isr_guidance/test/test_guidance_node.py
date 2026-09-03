"""Unit tests for guidance_node.py's _start_search resume guard (fixes the
120s TRACK/SEARCH belief-map-wipe defect — see ADR-018).

Needs rclpy + the built shark_isr_interfaces on the path, so run this via
`colcon test`, not bare pytest.
"""

import pytest
import rclpy

from shark_isr_guidance.guidance_node import GuidanceNode


@pytest.fixture
def node():
    rclpy.init()
    n = GuidanceNode()
    yield n
    n.destroy_node()
    rclpy.shutdown()


def test_resuming_same_area_preserves_belief_map(node):
    node._start_search(0.0, 0.0, 100.0, 30.0)
    bm_first = node._bayes_map
    bm_first.positive_detection(30.0, 0.0, sigma_m=15.0)  # give it real state
    peak_before = bm_first.max_probability()

    # Same call the mission makes on track/transit timeout to resume search.
    node._start_search(0.0, 0.0, 100.0, 30.0)

    assert node._bayes_map is bm_first          # not rebuilt
    assert node._bayes_map.max_probability() == peak_before  # belief preserved


def test_different_area_rebuilds_belief_map(node):
    node._start_search(0.0, 0.0, 100.0, 30.0)
    bm_first = node._bayes_map

    node._start_search(500.0, 500.0, 100.0, 30.0)  # genuinely new area

    assert node._bayes_map is not bm_first


def test_resume_still_resets_gate_and_candidate(node):
    node._start_search(0.0, 0.0, 100.0, 30.0)
    node._gate.on_detection(1.0)
    node._candidate = (10.0, 10.0, -31.9, 115.7)

    node._start_search(0.0, 0.0, 100.0, 30.0)

    assert node._gate.score == 0.0
    assert node._candidate is None


def test_strip_area_builds_real_region_and_threat_weights(node):
    node._start_search(0.0, 0.0, 0.0, 30.0, length_m=300.0, width_m=120.0, bearing_rad=0.0)

    assert node._region.length_m == 300.0
    assert node._region.width_m == 120.0
    assert node._threat_weights is not None
    assert len(node._threat_weights) == len(node._bayes_map.cells())


def test_lawnmower_uses_configured_lane_spacing(node):
    """LawnmowerStrategy's class default is 60 m (pre-ADR-010); the node must
    pass its own strip_width_m through."""
    node._strategy_name = 'lawnmower'
    node._start_search(0.0, 0.0, 100.0, 30.0)
    assert node._strategy._strip_width_m == node._strip_w


def test_mode_idle_drops_belief_map_so_next_mission_starts_fresh(node):
    from shark_isr_interfaces.srv import SetGuidanceMode
    node._start_search(0.0, 0.0, 100.0, 30.0)
    bm_first = node._bayes_map
    req = SetGuidanceMode.Request()
    req.mode = SetGuidanceMode.Request.MODE_IDLE
    node._srv_set_mode(req, SetGuidanceMode.Response())
    assert node._bayes_map is None
    node._start_search(0.0, 0.0, 100.0, 30.0)   # same area, new mission
    assert node._bayes_map is not bm_first


def test_mode_search_without_area_is_rejected_not_crashed(node):
    from shark_isr_interfaces.srv import SetGuidanceMode
    req = SetGuidanceMode.Request()
    req.mode = SetGuidanceMode.Request.MODE_SEARCH   # radius 0, length 0
    resp = node._srv_set_mode(req, SetGuidanceMode.Response())
    assert resp.accepted is False
    assert node._bayes_map is None


def test_circle_area_has_no_threat_weights(node):
    """The circle's SearchRegion is a fabricated square with no real
    shoreline — threat weighting must stay off for it."""
    node._start_search(0.0, 0.0, 100.0, 30.0)
    assert node._threat_weights is None
