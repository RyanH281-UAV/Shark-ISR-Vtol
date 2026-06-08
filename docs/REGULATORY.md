# Regulatory & Operational Notes

These are engineering/ops reminders, not legal advice. Confirm current rules with CASA before flying.

- **CASA applies.** Operating an RPA in Australia is governed by CASA. Requirements depend on weight,
  location, and whether the operation is recreational vs commercial/research. The Hornet at up to
  2.5 kg MTOW and any over-water/over-people or BVLOS operation likely raises additional obligations.
  Verify the current category, registration, accreditation/licensing, and any area approvals.
- **Over-water ISR is BVLOS-prone.** Persistent coastal monitoring tends toward beyond-visual-line-of-
  sight. BVLOS typically requires specific approvals — design the comms/telemetry and failsafe
  behaviour assuming it will be scrutinised.
- **Detection data is imagery of public spaces.** Privacy and data-handling expectations apply to any
  footage of beaches/people, separate from CASA. Log retention and access should be deliberate.
- **Software implications:**
  - Geofence + RTL behaviour must be configured in the autopilot and verified, not assumed.
  - The companion computer must never be able to override an autopilot failsafe.
  - Telemetry must record enough to reconstruct any incident from logs.

The autonomy stack does not enforce regulation, but it should make compliant operation easy:
clear geofence config, conservative failsafes, complete logs.
