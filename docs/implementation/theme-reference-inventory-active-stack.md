# Theme Reference Inventory (Active Stack)

This note inventories active theme references used by the canonical runtime stack (`src/` backend + `rpg-life-ui/` frontend) and clarifies scope boundaries for the 12-theme alignment change.

## Active Backend References (`src/`)

- `src/core/themes.py`
  - Canonical 12-theme constants/order/descriptions.
  - Idempotent repair helpers:
    - `ensure_user_themes(user_id)`
    - `ensure_skill_theme_mappings(user_id, skill_ids)`
- `src/ai/steps/rewards.py`
  - Runtime lazy repair calls before theme award derivation.
  - Per-theme propagation rule: full `max(1, round_half_up(skill_xp * 0.01))` for each mapped theme.
  - `source_skill_xp` stored as original skill award XP.
- `src/api/routes/users.py`
  - New-user bootstrap seeds canonical themes after L1 skill initialization.
- `src/api/routes/themes.py`
  - New API endpoint: `GET /api/themes` and `GET /api/v1/themes`.
  - Returns canonical theme DTOs sorted by canonical order.
- `src/scripts/backfill_themes_and_mappings.py`
  - One-time operational backfill for existing users and mappings.

## Active Frontend References (`rpg-life-ui/`)

- `rpg-life-ui/src/types/theme.ts`
  - Theme DTO contract for `/api/themes`.
- `rpg-life-ui/src/services/themes.service.ts`
  - API client for theme list endpoint.
- `rpg-life-ui/src/hooks/useThemes.ts`
  - React Query hook for theme list fetching.
- `rpg-life-ui/src/components/skills/ThemesList.tsx`
  - Renders true theme entities (not skill hierarchy roots).
- `rpg-life-ui/src/pages/ThemesSkills.tsx`
  - Themes tab now sources data from `useThemes`.
  - My Skills / Skill Tree remain hierarchy-driven views.

## Seed / Architecture Source-of-Truth Inputs

- `docs/architecture/COMPLETE_ARCHITECTURE.md`
- `data/seeds/kb/global_skills_v1.jsonl` (`related_themes`)
- `data/seeds/matcher/theme_mapping_v1.json`

## Out-of-Scope References

- Legacy `app/` stack theme references are intentionally out-of-scope for this change.
- Reason: active production/runtime path for this implementation is `src/` + `rpg-life-ui/`.
