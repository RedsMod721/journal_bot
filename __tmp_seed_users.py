import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path('data/db/rpg_life_tracker.db')
HIER_PATH = Path('data/seeds/kb/global_skill_hierarchy_v1.jsonl')

USERS = [
    ("1cf4f2e7-ccce-42d4-9f57-85ab00c6ab66", "alex_builder", "Alex Builder"),
    ("3f0f158d-d814-43f9-b035-5f6b43edeb41", "maya_motion", "Maya Motion"),
    ("37b80e12-c72a-4c2c-979a-68b02caae381", "leo_connector", "Leo Connector"),
]


def rank_from_level(level: int) -> str:
    if level < 10:
        return "F"
    if level < 20:
        return "E"
    if level < 30:
        return "D"
    if level < 40:
        return "C"
    if level < 50:
        return "B"
    if level < 60:
        return "A"
    if level < 75:
        return "S"
    if level < 100:
        return "SS"
    return "SSS"


hier = {}
with HIER_PATH.open('r', encoding='utf-8') as f:
    for line in f:
        row = json.loads(line)
        hier[row['skill_id']] = row

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("PRAGMA foreign_keys=ON")

cur.execute("SELECT id, source_skill_id, canonical_name, hierarchy_level FROM global_skills WHERE source_skill_id IS NOT NULL")
global_rows = cur.fetchall()
by_source = {r['source_skill_id']: r for r in global_rows}

hier = {k: v for k, v in hier.items() if k in by_source}
l1 = [k for k, v in hier.items() if v['hierarchy_level'] == 1]


def path_to_l1(skill_id, seen=None):
    seen = seen or set()
    if skill_id in seen:
        return None
    seen.add(skill_id)
    node = hier.get(skill_id)
    if not node:
        return None
    if node['hierarchy_level'] == 1:
        return [skill_id]
    for parent in node.get('parent_skill_ids', []):
        if parent not in hier:
            continue
        p = path_to_l1(parent, seen.copy())
        if p:
            return p + [skill_id]
    return None

chosen_path = None
for sid, node in hier.items():
    if node['hierarchy_level'] != 4:
        continue
    p = path_to_l1(sid)
    if not p:
        continue
    # accept shortest ancestor path that starts at L1 and ends at L4
    levels = [hier[x]['hierarchy_level'] for x in p]
    if levels[0] == 1 and levels[-1] == 4:
        chosen_path = p
        break
if not chosen_path:
    raise RuntimeError('Could not find L4 path in hierarchy/global_skills')

# ensure we have at least one L1 and one parent before L4
l1_main = chosen_path[0]
l4_main = chosen_path[-1]
parent_for_l4 = chosen_path[-2]


def pick_unlockables(activated_set, already, needed):
    picked = []
    for sid, node in hier.items():
        if sid in already:
            continue
        level = node['hierarchy_level']
        if level < 2 or level > 4:
            continue
        parents = node.get('parent_skill_ids', [])
        if any(p in activated_set for p in parents):
            picked.append(sid)
            already.add(sid)
            if len(picked) >= needed:
                break
    return picked

now = datetime.now(timezone.utc).isoformat()

for user_id, username, display_name in USERS:
    cur.execute("DELETE FROM user_skill_states WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM skills WHERE user_id = ?", (user_id,))

    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    exists = cur.fetchone() is not None
    email = f"{username}@placeholder.local"
    if exists:
        cur.execute(
            """
            UPDATE users
            SET email = ?, password_hash = ?, email_verified = ?, username = ?, display_name = ?,
                timezone = ?, language = ?, home_country = ?, allow_ip_geolocation = ?,
                learning_phase_complete = ?, quest_decisions_count = ?,
                confidence_threshold_instant = ?, confidence_threshold_longterm = ?,
                current_personality = ?, allow_trusted_nodes = ?, is_banned = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                email, "seeded_password_hash", 0, username, display_name,
                "UTC", "en", "FR", 0,
                0, 0,
                0.65, 0.45,
                "observer", 0, 0, now,
                user_id,
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO users (
                id, email, password_hash, email_verified, username, display_name,
                timezone, language, home_country, allow_ip_geolocation,
                learning_phase_complete, quest_decisions_count,
                confidence_threshold_instant, confidence_threshold_longterm,
                current_personality, allow_trusted_nodes, is_banned,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, email, "seeded_password_hash", 0, username, display_name,
                "UTC", "en", "FR", 0,
                0, 0,
                0.65, 0.45,
                "observer", 0, 0,
                now, now,
            ),
        )

    # 10 activated: one L1 + one parent of L4 + 8 additional L1
    extra_l1 = [sid for sid in l1 if sid != l1_main][:8]
    activated_ids = [l1_main, parent_for_l4] + extra_l1
    # Ensure uniqueness and exact size 10
    activated_ids = list(dict.fromkeys(activated_ids))[:10]
    while len(activated_ids) < 10:
        for sid in l1:
            if sid not in activated_ids:
                activated_ids.append(sid)
                if len(activated_ids) == 10:
                    break

    activated_set = set(activated_ids)

    # 5 unlocked_hidden: include one L4 + 4 additional unlockables
    already = set(activated_ids)
    unlocked_ids = [l4_main]
    already.add(l4_main)
    unlocked_ids.extend(pick_unlockables(activated_set, already, 4))
    if len(unlocked_ids) < 5:
        raise RuntimeError(f"Not enough unlockable skills for user {user_id}")

    # Skill rows for activated at level 20 (unlock gate satisfied)
    for sid in activated_ids:
        g = by_source[sid]
        cur.execute(
            """
            INSERT INTO skills (
                id, user_id, name, canonical_name, description,
                level, rank, xp, staleness, decay_paused, is_specialist_track,
                global_skill_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), user_id,
                g['canonical_name'], g['canonical_name'].lower().replace(' ', '_'), None,
                20, rank_from_level(20), 400, 0.0, 0, 0,
                g['id'], now, now,
            ),
        )

    # Skill rows for unlocked_hidden at level 1
    for sid in unlocked_ids:
        g = by_source[sid]
        cur.execute(
            """
            INSERT INTO skills (
                id, user_id, name, canonical_name, description,
                level, rank, xp, staleness, decay_paused, is_specialist_track,
                global_skill_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), user_id,
                g['canonical_name'], g['canonical_name'].lower().replace(' ', '_'), None,
                1, rank_from_level(1), 0, 0.0, 0, 0,
                g['id'], now, now,
            ),
        )

    blocked_target = activated_ids[-1]

    for sid in activated_ids:
        g = by_source[sid]
        cur.execute(
            """
            INSERT INTO user_skill_states (
                id, user_id, skill_id, state, user_blocked,
                activated_at, created_at, updated_at
            ) VALUES (?, ?, ?, 'activated', ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), user_id, g['id'],
                1 if sid == blocked_target else 0,
                now, now, now,
            ),
        )

    for sid in unlocked_ids:
        g = by_source[sid]
        parent_global = None
        for p in hier[sid].get('parent_skill_ids', []):
            if p in by_source:
                parent_global = by_source[p]['id']
                break
        cur.execute(
            """
            INSERT INTO user_skill_states (
                id, user_id, skill_id, state, user_blocked,
                unlocked_at, unlock_parent_skill_id, created_at, updated_at
            ) VALUES (?, ?, ?, 'unlocked_hidden', 0, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), user_id, g['id'],
                now, parent_global, now, now,
            ),
        )

conn.commit()

print('Seed complete.')
print('Chosen L4 path:', chosen_path)

for user_id, username, display_name in USERS:
    print(f'\\nUser: {display_name} ({user_id})')
    cur.execute("SELECT COUNT(*) FROM user_skill_states WHERE user_id=? AND state='activated'", (user_id,))
    activated = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM user_skill_states WHERE user_id=? AND state='unlocked_hidden'", (user_id,))
    unlocked = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM user_skill_states WHERE user_id=? AND state='activated' AND user_blocked=1", (user_id,))
    blocked_activated = cur.fetchone()[0]
    cur.execute(
        """
        SELECT MAX(gs.hierarchy_level)
        FROM user_skill_states uss
        JOIN global_skills gs ON gs.id = uss.skill_id
        WHERE uss.user_id=? AND uss.state IN ('activated','unlocked_hidden')
        """,
        (user_id,),
    )
    max_level = cur.fetchone()[0]

    cur.execute(
        """
        SELECT uss.skill_id, gs.source_skill_id
        FROM user_skill_states uss
        JOIN global_skills gs ON gs.id = uss.skill_id
        WHERE uss.user_id=? AND uss.state='unlocked_hidden'
        """,
        (user_id,),
    )
    unlocked_rows = cur.fetchall()

    violations = 0
    for row in unlocked_rows:
        sid = row['source_skill_id']
        parents = hier[sid].get('parent_skill_ids', []) if sid in hier else []
        ok = False
        for p in parents:
            if p not in by_source:
                continue
            pgid = by_source[p]['id']
            cur.execute(
                "SELECT level FROM skills WHERE user_id=? AND global_skill_id=? ORDER BY level DESC LIMIT 1",
                (user_id, pgid),
            )
            lvl_row = cur.fetchone()
            if lvl_row and int(lvl_row['level']) >= 20:
                ok = True
                break
        if not ok:
            violations += 1

    print(f'  activated={activated} | unlocked_hidden={unlocked} | activated_blocked={blocked_activated} | max_hierarchy_level={max_level} | unlock_rule_violations={violations}')

conn.close()
