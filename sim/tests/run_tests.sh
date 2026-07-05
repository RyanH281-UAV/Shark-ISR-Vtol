#!/usr/bin/env bash
# =============================================================================
#  SHARK ISR — SITL Test Runner  (T06–T10)
#
#  Run individual tests or all of them sequentially.
#  Each test exits 0 on PASS, 1 on FAIL.
#
#  Prerequisites before running any test:
#    Terminal 1:  ./scripts/run_sim.sh               (SITL + DDS agent)
#    Terminal 2:  source ros2_ws/install/setup.bash && ros2 launch shark_isr_autopilot autopilot.launch.py
#    Terminal 3:  source ros2_ws/install/setup.bash && ros2 launch shark_isr_guidance guidance.launch.py
#    Terminal 4:  source ros2_ws/install/setup.bash && ros2 launch shark_isr_mission mission.launch.py
#    Terminal 5:  source ros2_ws/install/setup.bash && ros2 launch shark_isr_perception perception.launch.py use_sim:=true
#               (required for T11 only; harmless to leave running for T06–T10)
#
#  Usage:
#    source ros2_ws/install/setup.bash
#    ./sim/tests/run_tests.sh           # run all T06–T11
#    ./sim/tests/run_tests.sh t06       # run single test
#    ./sim/tests/run_tests.sh t06 t08   # run subset
#
#  Test map:
#    t06  Orbit setpoint geometry          (autopilot only)
#    t07  Failsafe: offboard loss → exit   (autopilot only; KILLS bridge)
#    t08  CMD_ABORT → RTL                  (full stack)
#    t09  Low battery failsafe             (full stack)
#    t10  End-to-end mission rehearsal     (full stack, ~90s)
#    t11  Perception pipeline → TRACK      (full stack + perception, ~60s)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Map short names to scripts
declare -A TESTS=(
    [t06]="t06_orbit_setpoint.py"
    [t07]="t07_failsafe_offboard_loss.py"
    [t08]="t08_abort_rtl.py"
    [t09]="t09_low_battery_failsafe.py"
    [t10]="t10_e2e_rehearsal.py"
    [t11]="t11_perception_pipeline.py"
)
ALL_ORDER=(t06 t07 t08 t09 t10 t11)

run_test() {
    local key="$1"
    local script="${TESTS[$key]}"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Running ${key^^}: ${script}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if python3 "${SCRIPT_DIR}/${script}"; then
        echo "  ✓ ${key^^} passed"
        return 0
    else
        echo "  ✗ ${key^^} FAILED"
        return 1
    fi
}

# Parse args
if [[ $# -eq 0 ]]; then
    SELECTED=("${ALL_ORDER[@]}")
else
    SELECTED=("$@")
fi

PASS=0
FAIL=0
FAILED_TESTS=()

for key in "${SELECTED[@]}"; do
    key="${key,,}"   # lowercase
    if [[ -z "${TESTS[$key]+x}" ]]; then
        echo "Unknown test: $key (valid: ${!TESTS[*]})"
        exit 1
    fi
    # $((...)) not ((PASS++)): post-increment returns the OLD value, so ((PASS++))
    # with PASS=0 exits 1 and set -e kills the runner after the first test.
    if run_test "$key"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILED_TESTS+=("$key")
    fi
    # Inter-test gap — let SITL settle between tests
    sleep 5
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: ${PASS} passed, ${FAIL} failed"
if [[ ${#FAILED_TESTS[@]} -gt 0 ]]; then
    echo "  Failed:  ${FAILED_TESTS[*]}"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
[[ $FAIL -eq 0 ]]
