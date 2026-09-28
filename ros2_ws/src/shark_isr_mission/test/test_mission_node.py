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


# ── CMD_START altitudes and orbit radius (2026-09-28) ─────────────────────────
# Altitudes arrive AMSL and must become height above home; the orbit radius
# must actually reach guidance.

from geometry_msgs.msg import Point  # noqa: E402
from shark_isr_interfaces.msg import VehicleState  # noqa: E402
from shark_isr_interfaces.srv import MissionCommand  # noqa: E402


def _vehicle(amsl_m: float, z_above_home_m: float) -> VehicleState:
    v = VehicleState()
    v.position_valid = True
    v.latitude_deg, v.longitude_deg = -31.998, 115.748
    v.altitude_amsl_m = amsl_m
    v.position_enu_m = Point(x=0.0, y=0.0, z=z_above_home_m)
    return v


class _FakeClient:
    """Records service requests instead of sending them."""
    def __init__(self):
        self.requests = []

    def call_async(self, req):
        self.requests.append(req)

        class _F:
            def add_done_callback(self, cb):
                pass
        return _F()


def _start(node, **fields):
    req = MissionCommand.Request()
    req.command = MissionCommand.Request.CMD_START
    req.search_lat_deg, req.search_lon_deg = -31.998, 115.748
    for k, v in fields.items():
        setattr(req, k, v)
    return node._srv_mission_command(req, MissionCommand.Response())


def test_start_converts_amsl_to_height_above_home(node):
    node._cli_ap = _FakeClient()
    node._vehicle = _vehicle(amsl_m=20.0, z_above_home_m=0.0)   # home 20 m AMSL
    resp = _start(node, transit_alt_amsl_m=70.0, search_alt_amsl_m=50.0)
    assert resp.accepted
    assert node._transit_alt == 50.0
    assert node._search_alt == 30.0


def test_start_mid_flight_uses_home_not_current_altitude(node):
    node._cli_ap = _FakeClient()
    node._vehicle = _vehicle(amsl_m=70.0, z_above_home_m=50.0)  # home still 20 m
    _start(node, transit_alt_amsl_m=70.0, search_alt_amsl_m=50.0)
    assert node._search_alt == 30.0


def test_start_rejects_altitude_outside_envelope(node):
    node._cli_ap = _FakeClient()
    node._vehicle = _vehicle(amsl_m=25.0, z_above_home_m=0.0)
    resp = _start(node, transit_alt_amsl_m=30.0, search_alt_amsl_m=30.0)  # 5 m
    assert not resp.accepted
    assert node._phase == MissionPhase.IDLE
    assert node._cli_ap.requests == []            # never armed


def test_start_rejects_without_global_position(node):
    node._cli_ap = _FakeClient()
    v = _vehicle(amsl_m=0.0, z_above_home_m=0.0)
    v.latitude_deg = v.longitude_deg = 0.0
    node._vehicle = v
    assert not _start(node, search_alt_amsl_m=30.0).accepted


def test_orbit_radius_reaches_guidance_and_is_not_sticky(node):
    node._cli_ap = _FakeClient()
    node._cli_gd = _FakeClient()
    node._vehicle = _vehicle(amsl_m=0.0, z_above_home_m=0.0)
    _start(node, search_alt_amsl_m=30.0, orbit_radius_m=80.0)
    node._do_transit()
    node._start_search()
    assert [r.orbit_radius_m for r in node._cli_gd.requests] == [80.0, 80.0]

    node._phase = MissionPhase.IDLE              # next mission, radius omitted
    _start(node, search_alt_amsl_m=30.0)
    assert node._orbit_radius == 0.0             # guidance default, not 80
