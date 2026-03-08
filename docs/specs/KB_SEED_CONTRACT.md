# KB Seed Contract (`src/` Canonical)

This document defines the canonical file naming and placement contract for Week 2.5/Week 3 seed assets.

## Canonical Paths

Seed files MUST exist at these paths:

- `data/seeds/kb/global_skills_v1.jsonl`
- `data/seeds/kb/global_skill_hierarchy_v1.jsonl`
- `data/seeds/kb/global_quests_v1.jsonl`
- `data/seeds/kb/global_insights_v1.jsonl`
- `data/seeds/kb/rag_documents_v1.jsonl`

Matcher artifacts MUST exist at these paths:

- `data/seeds/matcher/quest_templates_v1.json`
- `data/seeds/matcher/theme_mapping_v1.json`

## Source Rename Mapping

When importing master exports, rename as follows:

- `skills_master.jsonl` -> `global_skills_v1.jsonl`
- `skill_hierarchy_master.jsonl` -> `global_skill_hierarchy_v1.jsonl`
- `quest_templates_master.jsonl` -> `global_quests_v1.jsonl`
- `insights_master.jsonl` -> `global_insights_v1.jsonl`
- `master_rag.jsonl` -> `rag_documents_v1.jsonl`

## Validation Baselines

Minimum accepted row counts:

- skills: `>=500`
- skill hierarchy rows: `>=500`
- quests: `>=200`
- insights: `>=1000`
- rag documents: `>=1000`

Current expected full-corpus counts:

- skills: `607`
- skill hierarchy rows: `607`
- quests: `1875`
- insights: `2115`
- rag documents: `1250`

Upper bounds are intentionally not enforced for full-corpus operation.

## Artifact Contract

`quest_templates_v1.json` and `theme_mapping_v1.json` MUST:

- set `schema_version` to `1`
- be deterministic outputs from canonical seed inputs
- have hashes stored in `server_config` keys:
  - `quest_matcher.templates_path`
  - `quest_matcher.templates_sha256`
  - `quest_matcher.theme_mapping_path`
  - `quest_matcher.theme_mapping_sha256`

## Required Scripts

- Import and artifact generation: `python scripts/seeding/import_kb_master.py`
- Seed and artifact validation: `python scripts/validation/validate_preseed_kb.py --strict-artifacts`
- Week 3 preflight with seed contract: `python scripts/validation/week3_preflight.py --require-runtime-deps --require-seed-artifacts`
