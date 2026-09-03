"""Unit tests for mission_node.py's guidance-phase mirror (ADR-018).

Regression test for the TRANSITING gap: the mission used to have separate
SEARCHING/TRACKING branches and no TRANSITING one, so it sat in TRANSITING
for up to transit_timeout_s after guidance had already reached SEARCH.

Needs rclpy + the built shark_isr_interfaces on the path, so run this via
`colcon test`, not bare pytest.
"""

import pytest
import rclpy

from shark_isr_interfaces.msg import SearchState
from shark_isr_mission.mission_node import MissionNode, MissionPhase


@pytest.fixture
def node():
    rclpy.init()
    n = MissionNode()
    yield n
    n.destroy_node()
    rclpy.shutdown()


def _search_state(phase: int) -> SearchState:
    msg = SearchState()
    msg.phase = phase
    return msg


def test_mirrors_transit_to_search(node):
    """The gap this test guards: TRANSITING must follow guidance into
    SEARCHING without waiting for transit_timeout_s."""
    node._phase = MissionPhase.TRANSITING
    node._cb_search_state(_search_state(SearchState.PHASE_SEARCH))
    assert node._phase == MissionPhase.SEARCHING


def test_mirrors_search_to_track(node):
    node._phase = MissionPhase.SEARCHING
    node._cb_search_state(_search_state(SearchState.PHASE_TRACK))
    assert node._phase == MissionPhase.TRACKING


def test_mirrors_track_to_search(node):
    node._phase = MissionPhase.TRACKING
    node._cb_search_state(_search_state(SearchState.PHASE_SEARCH))
    assert node._phase == MissionPhase.SEARCHING


@pytest.mark.parametrize('phase', [
    MissionPhase.IDLE, MissionPhase.STARTING, MissionPhase.PAUSED,
    MissionPhase.RETURNING, MissionPhase.LANDED,
])
def test_does_not_mirror_during_mission_owned_phases(node, phase):
    """A stray SearchState must not knock the mission out of a phase it
    owns itself (e.g. mid-PAUSE or mid-RETURN)."""
    node._phase = phase
    node._cb_search_state(_search_state(SearchState.PHASE_TRACK))
    assert node._phase == phase
