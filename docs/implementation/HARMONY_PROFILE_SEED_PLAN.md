# Harmony Profile Seed Plan

## Goal

Define the minimum profile data needed to render the current harmony card on the Profile screen, keep future seed generation compliant with the live Week 5 implementation, and provide three deterministic demo profiles that exercise distinct harmony shapes.

Reference seed artifact:

- `data/seeds/demo/harmony_profiles_v1.json`
- `scripts/seeding/seed_harmony_profiles.py`

Reference time:

- `2026-03-11T12:00:00Z`

## UI Quick Pick

Use these seeded users in the Profile screen:

- `Maya Motion` (`3f0f158d-d814-43f9-b035-5f6b43edeb41`): balanced polygon, badge `Balanced`, overall `88%`
- `Leo Connector` (`37b80e12-c72a-4c2c-979a-68b02caae381`): social-heavy asymmetric polygon, badge `Balanced`, overall `55%`
- `Alex Builder` (`1cf4f2e7-ccce-42d4-9f57-85ab00c6ab66`): overworked profile, badge `Warning`, overall `27%`

## What The Harmony Card Actually Needs

The current UI component (`rpg-life-ui/src/components/dashboard/HarmonyRadarChart.tsx`) renders from `GET /harmony/dimensions` and only needs:

- `user_id`
- `dimensions.physical`
- `dimensions.mental`
- `dimensions.social`
- `dimensions.productivity`
- `dimensions.rest`
- `dimensions.growth`
- `dimensions.creative`
- `overall_balance`
- `overwork_stage`
- `overwork_consecutive_days`
- `updated_at`

That response is derived, not authored directly. A profile therefore needs these upstream inputs to produce non-placeholder harmony content:

- `users.id`
- `users.timezone`
- `forgiveness_configs.preset`
- canonical user `themes` rows when `skills_themes_involved` is used
- `journal_entries.status='completed'`
- `journal_entries.created_at` inside the active harmony window
- `journal_entries_structured.energy_level` for overwork escalation quality
- either `journal_entries_structured.task_type` or `journal_entries_structured.skills_themes_involved`

Optional but recommended for the full Profile screen:

- `strategy_tracking` via `BalanceWindowService.refresh_window(...)` so the Variety card renders
- pre-existing user skills/themes if you want non-zero profile stats outside harmony

## Important Implementation Notes

- The live code currently computes harmony from a 7-day window, not 30 days.
- Theme-linked classification is the easiest compliant seed path because one entry can address multiple harmony dimensions through `skills_themes_involved`.
- Overwork badges are persistence-based. To show `Watch`, `Warning`, or `Crisis`, seeding must replay `refresh_harmony(..., advance_overwork_state=True)` across multiple local days.
- Read-only harmony fetches must use `advance_overwork_state=False`.
- Snapshots should be created through `HarmonyRefreshService.create_snapshot(...)`, not hand-written.

## Three Demo Profiles

These are the seeded scenarios in `harmony_profiles_v1.json`.

### 1. Maya Motion

- Scenario: `balanced_generalist`
- Purpose: show a high, well-rounded polygon with no overwork warning
- Verified output:
  - physical `1.0`
  - mental `0.75`
  - social `1.0`
  - productivity `0.8`
  - rest `1.0`
  - growth `1.0`
  - creative `1.0`
  - overall balance `0.88445`
  - overwork stage `0`

### 2. Leo Connector

- Scenario: `social_explorer`
- Purpose: show a visibly asymmetric but still functional profile driven by social, mental, and growth-heavy activity
- Verified output:
  - physical `0.33333`
  - mental `1.0`
  - social `1.0`
  - productivity `0.4`
  - rest `0.57143`
  - growth `1.0`
  - creative `0.5`
  - overall balance `0.54628`
  - overwork stage `0`

### 3. Alex Builder

- Scenario: `overworked_builder`
- Purpose: show the warning-state harmony card with visible consecutive-day overwork messaging
- Verified output:
  - physical `0.0`
  - mental `1.0`
  - social `0.33333`
  - productivity `1.0`
  - rest `0.14286`
  - growth `1.0`
  - creative `0.0`
  - overall balance `0.27257`
  - overwork stage `2`
  - overwork consecutive days `4`

## Generation Plan

For future harmony-profile generation, keep this sequence:

1. Upsert the demo user identity and timezone.
2. Ensure canonical themes exist for that user.
3. Upsert the forgiveness preset before any harmony refresh.
4. Clear only the runtime-derived harmony/profile state for the demo user:
   - journal entries
   - structured journal rows
   - harmony rows
   - harmony snapshots
   - strategy tracking
5. Seed completed journal entries with deterministic timestamps inside the 7-day window.
6. Seed `skills_themes_involved` using live theme IDs, not hard-coded UUIDs.
7. Rebuild harmony through `HarmonyRefreshService`.
8. For warning/crisis profiles, replay write-path refreshes across local days.
9. Rebuild strategy tracking through `BalanceWindowService.refresh_window(...)`.
10. Re-run one final read-only harmony refresh and assert exact expected values.

## Current Local DB Caveat

The checked-in dev database at `data/db/rpg_life_tracker.db` is still on a legacy harmony/strategy schema, so this seed cannot be applied there without a schema rebuild or clean Week 5 database. The seed flow was validated successfully against a fresh Week 5 SQLite database at:

- `data/db/harmony_profiles_validation.db`

## Validation Commands

```powershell
$env:DATABASE_URL='sqlite:///c:/Users/vazqse01/journal_bot/data/db/harmony_profiles_validation.db'
.\.venv\Scripts\python.exe -c "import src.db.models; from src.db.session import init_db; init_db()"
.\.venv\Scripts\python.exe scripts/seeding/seed_harmony_profiles.py
```
