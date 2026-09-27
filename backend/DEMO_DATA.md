# Demo data

**Every record created by `backend/seed_demo_data.py` is fabricated.** No real
person, complaint, case, or recording is in this repository or in any database
this script creates. The staff accounts are fictional demo identities and the
password is printed in the console on purpose.

Regenerate at any time:

```bash
cd backend
python seed_demo_data.py --reset     # drops and rebuilds every table
python seed_demo_data.py --summarise # read-only counts, no writes
```

The seed is idempotent-ish: running it without `--reset` against a database
that already contains cases logs a warning and does nothing, so it cannot
silently duplicate demo records.

---

## What gets created

| Thing | Count | Notes |
|---|---|---|
| Staff accounts | 5 | 2 counsellors, 1 district admin, 1 state admin, 1 police liaison |
| Chat cases | 9 | spanning all four bands, four of them in Hindi |
| IVRS case | 1 | `LOW-2`, Hindi, keypad presses recorded |
| Voice case | 1 | synthetic generated clip, labelled `synthetic_demo` |
| Audio analyses | 1 | heuristic extractor, marked as a demo signal |
| SVI rows | 11 | one per case, recomputed through the real ingest pipeline |
| Recommendation rows | 11 | deterministic rules, not language-model output |
| Audit rows | many | every seed action is attributed to a named demo actor |

### Band distribution after seeding

`python seed_demo_data.py --summarise` on a fresh database reports:

```json
{
  "cases": 11,
  "risk_distribution": { "Low": 3, "Moderate": 2, "High": 2, "Critical": 4 },
  "critical_overrides": 4,
  "human_safety_actions_recorded": 1,
  "outbox_rows": 24,
  "svi_rows": 11,
  "recommendation_rows": 11,
  "disclosure_rows": 0
}
```

Three Low cases because the voice case also lands in Low. Every one of the
four Critical cases is override-backed, which is explained further down.

### Staff logins

Password for all of them: `demo-counsellor-14566`

| Pseudonym ID | Role | District | Sees |
|---|---|---|---|
| `staff.counsellor.1` | counsellor | Bhopal | Own district queue |
| `staff.counsellor.2` | counsellor | Indore | Own district queue |
| `admin.district.mp` | district_admin | Bhopal | Bhopal only |
| `admin.state.mp` | state_admin | all | State-wide analytics and audit |
| `police.liaison.mp` | law_enforcement | all | Referred cases only, minimal projection |

The district split between the two counsellors is deliberate: log in as
`staff.counsellor.1` and Bhopal cases appear while Indore cases do not. That
single fact demonstrates that access control is enforced server-side, which a
judge can verify in about fifteen seconds.

---

## The ten text scenarios

`expected_band` below is the authoring hint used to build the demo table. It is
**not** an assertion about the engine: the live engine decides the band. A
pytest case (`tests/test_demo_data_integrity.py`) runs this exact seed against a
throwaway database and fails if a scenario's hint and the engine's output ever
disagree, so the table cannot quietly start lying.

| Hint | District | Lang | Channel | What it shows | Engine result |
|---|---|---|---|---|---|
| `LOW-1` | Bhopal | en | chat | Wants information about a property dispute. No distress indicators. | Low, no override |
| `LOW-2` | Indore | **hi** | **ivrs** | A Hindi phone-menu enquiry for helpline numbers only. Keypad presses `1,1,3`. | Low, no override |
| `MOD-1` | Bhopal | en | chat | Weeks of poor sleep, anxiety, and some hopelessness. Wants someone to talk to. | Moderate |
| `MOD-2` | Indore | **hi** | chat | Hindi: isolation and low mood, seeking a callback. | Moderate |
| `HIGH-1` | Bhopal | en | chat | Repeated threats and intimidation, and distrust of support systems. | High |
| `HIGH-2` | Indore | **hi** | chat | Hindi: economic coercion plus threats from a family member. | High |
| `CRIT-4` | Bhopal | en | chat | A child locked in a room. **Override fires on child safety even though the composite is 52.9.** | Critical by override |
| `CRIT-1` | Bhopal | en | chat | "I do not want to live any more." Composite crosses 75 *and* a critical flag fires. | Critical (75.9) |
| `CRIT-2` | Indore | **hi** | chat | Hindi: immediate danger stated plainly. Left mid-response with `safety_contact` already recorded, so the close gate can be seen refusing. | Critical by override |
| `CRIT-3` | Bhopal | en | chat | Ongoing harm plus a crisis statement. **Two** critical-tier flags on one case. Pre-referred to police liaison. | Critical by override |

Four of the ten are in Hindi, and one of those is on the IVRS channel, so the
demo covers all three channels without a separate "language demo" section.

### The three cases worth looking at

**`CRIT-4` is the most instructive row in the table.** Its composite score is
52.9, which is in the middle of the High band. The case still lands in Critical
because `child_safety_concern` is declared `tier: critical` in the English and
Hindi lexicons. This is the Critical Override doing exactly what it exists for:
a numeric blend should not be able to talk the system down when a child's
safety is in question.

**`CRIT-1` is the only case that crosses the 75 threshold on its own composite**
(75.9), and it happens to also carry a critical-tier flag, so both mechanisms
fire on the same record.

**`CRIT-2` is pre-loaded to demonstrate a refusal.** The seed records a
`safety_contact` action but not an `emergency_bridge`, which is exactly the
half-complete state the close gate exists to catch. Opening this case as a
counsellor and trying to close it returns a 409 and names the missing action.
That is a better demo than a case that closes successfully, because it shows the
guardrail working rather than merely present.

**Every other Critical case is override-backed.** That is a real property of the
current calibration, not a coincidence. The text-only weights are 0.6/0.4, and
the behavioural component rarely climbs above about 20 in genuine
conversations, so the composite only reaches 75 when the text score is close to
saturation. In practice the numeric threshold is a backstop rather than the main
route into the top band. `test_critical_is_in_practice_reached_through_the_override`
pins this down so that if it ever changes, a human decides whether the demo
should keep showing it.

---

## The voice case

`VOICE-1` seeds a 13-second clip generated by
`nlp.audio_analyzer.generate_demo_clip`. It is **not a recording of a person.**

Three things make that impossible to miss:

- The stored `AudioAnalysis.notes` contains `synthetic_demo_signal`.
- The `method` field is `heuristic-demo`, never a trained-model label.
- The victim-facing UI copy for the demo button says, in the words shown to the
  person: *"This is a computer-generated practice clip, not a recording of you."*

The clip lands in the **Low** band. That surprises people who expect the
"stressed" clip to score high, and the honest answer is that a synthesized
waveform is far calmer than a real distressed voice — the demo clip
demonstrates that the voice path is wired end to end, not that the extractor
can grade human distress. `tests/test_demo_data_integrity.py` asserts the
`synthetic` marker survives into the stored row so this cannot quietly change.

---

## What the seed deliberately does not create

- **No complainant identity.** No names, no phone numbers, no addresses. The
  `User` row has a random pseudonym and a district, nothing else.
- **No closed cases.** Every case is open, because the demo is more useful when
  the judge can perform the close themselves and watch the safety gate refuse
  them.
- **No auto-referral to police.** `CRIT-3` arrives pre-referred so the
  law-enforcement view is not empty on arrival, but the referral is an
  explicitly recorded human action with a named actor, never an automatic
  consequence of a score.
- **No real helpline numbers beyond the public ones.** Tele MANAS 14416,
  Women Helpline 181, Police 112, NHAA 14566. These are the real published
  numbers, re-verified against the source before any real deployment.

---

## Resetting

`--reset` calls `reset_schema()`, which drops every table and recreates it. It
is destructive and there is no confirmation prompt, because the script's only
intended target is a demo database. Never point it at anything you care about:

```bash
# destructive
python seed_demo_data.py --reset
```

If you only want to see what is there:

```bash
python seed_demo_data.py --summarise   # read-only
```
