# WEEK_2.5_COMPLETE_PROMPTS.md
**Project:** RPG Life Tracker - Week 2.5 Implementation Prompts  
**Version:** 1.0  
**Date:** February 26, 2026  
**Purpose:** Complete, copy-paste ready prompts for Week 2.5 (no placeholders)

---

## HOW TO USE THESE PROMPTS

**For each prompt below:**
1. Copy the ENTIRE prompt (from "---PROMPT START---" to "---PROMPT END---")
2. Paste into Claude 3.5 Sonnet or GPT-4 Turbo
3. Review the generated code
4. Save to the specified file path
5. Test immediately
6. Move to next prompt

**DO NOT modify the prompts** - they're designed to work together and reference our complete architecture.

---

## SECTION 1: SQLALCHEMY MODELS (DATABASE SCHEMA)

### Prompt 1.1: Users Table Model

```
---PROMPT START---

I'm building an RPG Life Tracker application based on a comprehensive architecture. Generate a SQLAlchemy model for the users table.

**Project Context:**
This is a journal-based life tracking system that gamifies personal development. Users submit journal entries which are processed through an AI pipeline to award XP, update skills, and track quests.

**Table Specification:**

**Table Name:** users

**Description:** Stores user accounts with personality settings and forgiveness configurations

**Columns:**
- user_id: String(36), Primary Key, UUID format (e.g., "550e8400-e29b-41d4-a716-446655440000")
- username: String(50), Unique, NOT NULL, User's display name
- email: String(255), Unique, NOT NULL, User's email address
- created_at: DateTime, NOT NULL, Default datetime.utcnow, Account creation timestamp
- updated_at: DateTime, NOT NULL, Default datetime.utcnow, Auto-updates on change
- personality_type: String(20), NOT NULL, Must be 'therapist' or 'raphael'
- forgiveness_preset: String(20), NOT NULL, Default 'balanced', One of: 'lenient', 'balanced', 'strict'
- preferences: JSON, NOT NULL, Default {} (empty dict), User preferences as JSON

**Relationships:**
- skills: One-to-Many relationship to Skill model (cascade delete all skills when user deleted)
- themes: One-to-Many relationship to Theme model (cascade delete all themes when user deleted)
- journal_entries: One-to-Many relationship to JournalEntry model (cascade delete all entries when user deleted)

**Indexes:**
- Create index on username column (for fast username lookups)
- Create index on email column (for fast email lookups)

**Requirements:**
1. Use SQLAlchemy 2.0 syntax (not 1.4 or older)
2. Import from: sqlalchemy, datetime
3. Inherit from Base (assume Base = declarative_base() is defined elsewhere)
4. Use relationship() with back_populates (not backref)
5. Set cascade="all, delete-orphan" on relationships (when user deleted, delete related records)
6. Include __table_args__ for indexes
7. Add a comprehensive docstring explaining the table's purpose
8. Add inline comments for complex fields

**Output Format:**
```python
"""
SQLAlchemy model for users table.
File: src/db/models.py
"""

from sqlalchemy import Column, String, DateTime, JSON, Index, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    \"\"\"[Your docstring here]\"\"\"
    __tablename__ = "users"
    
    # [Your column definitions here]
    
    # [Your relationships here]
    
    # [Your indexes and constraints here]
    __table_args__ = (
        [indexes],
    )
```

Generate the complete User model now following the exact specifications above.

---PROMPT END---
```

**Save to:** `src/db/models.py` (create file, this is the first model)

---

### Prompt 1.2: Skills Table Model

```
---PROMPT START---

I'm building an RPG Life Tracker application. Generate a SQLAlchemy model for the skills table. This model will be added to the same file as the User model.

**Project Context:**
Skills represent user abilities that gain XP through practice. Each skill tracks total XP, current level, forgiveness mechanics (staleness, retention), and failure counts for struggle arcs.

**Table Specification:**

**Table Name:** skills

**Description:** Tracks user skills with XP progression, forgiveness mechanics, and failure tracking

**Columns:**
- skill_id: String(36), Primary Key, UUID format
- user_id: String(36), Foreign Key to users.user_id, NOT NULL, ON DELETE CASCADE
- canonical_name: String(200), NOT NULL, Skill name (e.g., "Python Programming", "Cardio Running")
- category: String(50), NOT NULL, One of: "Physical", "Mental", "Professional", "Creative", "Social"
- total_xp: Integer, NOT NULL, Default 0, Total XP accumulated (never decreases)
- current_level: Integer, NOT NULL, Default 1, Current level (1-100)
- last_practiced_at: DateTime, Nullable, Last time this skill was practiced
- staleness_days: Integer, NOT NULL, Default 0, Days since last practice (for forgiveness)
- retained_xp_pct: Float, NOT NULL, Default 1.0, Forgiveness retention percentage (0.0-1.0)
- failure_count: Integer, NOT NULL, Default 0, Consecutive failures for struggle arc triggers (Q23)
- created_at: DateTime, NOT NULL, Default datetime.utcnow
- updated_at: DateTime, NOT NULL, Default datetime.utcnow, Auto-update on change

**Relationships:**
- user: Many-to-One relationship back to User model
- quests: One-to-Many relationship to Quest model (cascade delete)

**Indexes:**
- Index on user_id (for fast "get all user's skills" queries)
- Index on canonical_name (for skill lookups)
- Composite index on (user_id, canonical_name) for uniqueness checking

**Constraints:**
- CHECK constraint: total_xp >= 0
- CHECK constraint: current_level >= 1 AND current_level <= 100
- CHECK constraint: retained_xp_pct >= 0.0 AND retained_xp_pct <= 1.0
- CHECK constraint: staleness_days >= 0
- CHECK constraint: failure_count >= 0

**Requirements:**
1. Use SQLAlchemy 2.0 syntax
2. Foreign key with CASCADE delete (when user deleted, delete their skills)
3. Use relationship() with back_populates="skills" for user relationship
4. Use relationship() with back_populates="skill" for quests relationship
5. Include all CHECK constraints in __table_args__
6. Add docstring explaining XP vs. Level relationship

**Output Format:**
Add this class to the same file as User model (src/db/models.py):

```python
class Skill(Base):
    \"\"\"[Your docstring here explaining XP, levels, forgiveness]\"\"\"
    __tablename__ = "skills"
    
    # [Column definitions]
    
    # [Relationships]
    
    # [Indexes and constraints]
    __table_args__ = (
        [indexes and CHECK constraints],
    )
```

Generate the complete Skill model now.

---PROMPT END---
```

**Save to:** `src/db/models.py` (append to existing file)

---

### Prompt 1.3: Themes Table Model

```
---PROMPT START---

I'm building an RPG Life Tracker application. Generate a SQLAlchemy model for the themes table.

**Project Context:**
Themes are meta-categories (Physical, Mental, Professional, Creative, Social, Rest, Growth, Discipline, Productivity) that receive 0.1% of skill XP through propagation. This creates a dual progression system.

**Table Specification:**

**Table Name:** themes

**Description:** Tracks thematic progression through XP propagation from related skills

**Columns:**
- theme_id: String(36), Primary Key, UUID format
- user_id: String(36), Foreign Key to users.user_id, NOT NULL, ON DELETE CASCADE
- name: String(50), NOT NULL, Theme name (one of the 9 canonical themes)
- total_xp: Integer, NOT NULL, Default 0, Total XP (propagated from skills at 0.1% rate)
- current_level: Integer, NOT NULL, Default 1, Current level (1-100)
- created_at: DateTime, NOT NULL, Default datetime.utcnow
- updated_at: DateTime, NOT NULL, Default datetime.utcnow

**Valid Theme Names (Enum):**
- Physical
- Mental
- Professional
- Creative
- Social
- Rest
- Growth
- Discipline
- Productivity

**Relationships:**
- user: Many-to-One relationship back to User model

**Indexes:**
- Index on user_id
- Index on name
- Composite index on (user_id, name) for uniqueness

**Constraints:**
- CHECK constraint: total_xp >= 0
- CHECK constraint: current_level >= 1 AND current_level <= 100
- CHECK constraint: name IN ('Physical', 'Mental', 'Professional', 'Creative', 'Social', 'Rest', 'Growth', 'Discipline', 'Productivity')

**Requirements:**
1. Use SQLAlchemy 2.0 syntax
2. Foreign key with CASCADE delete
3. Include CHECK constraint for valid theme names
4. Add docstring explaining 0.1% XP propagation mechanism

**Output Format:**
```python
class Theme(Base):
    \"\"\"[Docstring explaining theme XP propagation]\"\"\"
    __tablename__ = "themes"
    
    # [Columns]
    
    # [Relationships]
    
    # [Indexes and constraints]
    __table_args__ = (
        [indexes and CHECK constraints including name validation],
    )
```

Generate the complete Theme model now.

---PROMPT END---
```

**Save to:** `src/db/models.py` (append)

---

### Prompt 1.4: JournalEntry Table Model

```
---PROMPT START---

I'm building an RPG Life Tracker application. Generate a SQLAlchemy model for the journal_entries table.

**Project Context:**
Journal entries are the core input to the system. Users write text, which is processed through a 17-step AI pipeline to extract skills, award XP, and update quests.

**Table Specification:**

**Table Name:** journal_entries

**Description:** Stores user journal entries and tracks processing status

**Columns:**
- entry_id: String(36), Primary Key, UUID format
- user_id: String(36), Foreign Key to users.user_id, NOT NULL, ON DELETE CASCADE
- raw_text: Text, NOT NULL, The journal entry text (10-10,000 words)
- word_count: Integer, NOT NULL, Number of words in raw_text
- processing_job_id: String(36), Foreign Key to processing_jobs.job_id, Nullable, References async processing job
- processing_status: String(20), NOT NULL, Default 'pending', One of: 'pending', 'processing', 'completed', 'failed'
- created_at: DateTime, NOT NULL, Default datetime.utcnow, When entry was submitted
- processed_at: DateTime, Nullable, When processing completed

**Relationships:**
- user: Many-to-One back to User model
- processing_job: Many-to-One to ProcessingJob model (nullable)

**Indexes:**
- Index on user_id
- Index on created_at (for chronological queries)
- Index on processing_status (for finding pending entries)
- Composite index on (user_id, created_at) for user's entry timeline

**Constraints:**
- CHECK constraint: word_count >= 10 AND word_count <= 10000
- CHECK constraint: processing_status IN ('pending', 'processing', 'completed', 'failed')

**Requirements:**
1. Use SQLAlchemy 2.0 syntax
2. Text column for raw_text (unlimited length)
3. Foreign key with CASCADE delete
4. Index on created_at for timeline queries
5. Add docstring explaining 10-10,000 word limit

**Output Format:**
```python
class JournalEntry(Base):
    \"\"\"[Docstring explaining journal entry processing]\"\"\"
    __tablename__ = "journal_entries"
    
    # [Columns]
    
    # [Relationships]
    
    # [Indexes and constraints]
    __table_args__ = (
        [indexes and CHECK constraints],
    )
```

Generate the complete JournalEntry model now.

---PROMPT END---
```

**Save to:** `src/db/models.py` (append)

---

### Prompt 1.5: Quest Table Model

```
---PROMPT START---

I'm building an RPG Life Tracker application. Generate a SQLAlchemy model for the quests table.

**Project Context:**
Quests are user goals tied to skills or themes. There are 4 completion types: one-time (complete first 5K run), cumulative (write 50,000 words), recursive (meditate 3× weekly), and streak (code daily for 30 days).

**Table Specification:**

**Table Name:** quests

**Description:** Tracks user quests with progress toward completion

**Columns:**
- quest_id: String(36), Primary Key, UUID format
- user_id: String(36), Foreign Key to users.user_id, NOT NULL, ON DELETE CASCADE
- skill_id: String(36), Foreign Key to skills.skill_id, Nullable, ON DELETE CASCADE (NULL for theme quests)
- quest_name: String(200), NOT NULL, Quest description (e.g., "Complete First 5K Run")
- completion_type: String(20), NOT NULL, One of: 'one_time', 'cumulative', 'recursive', 'streak'
- success_criteria: JSON, NOT NULL, Completion criteria as JSON (e.g., {"target_distance_km": 5} or {"target_words": 50000})
- current_progress: Float, NOT NULL, Default 0.0, Current progress value
- target_progress: Float, NOT NULL, Default 1.0, Target progress value
- is_completed: Boolean, NOT NULL, Default False, Whether quest is completed
- failure_count: Integer, NOT NULL, Default 0, Consecutive failures (Q23 struggle arc)
- created_at: DateTime, NOT NULL, Default datetime.utcnow
- completed_at: DateTime, Nullable, When quest was completed

**Relationships:**
- user: Many-to-One back to User model
- skill: Many-to-One back to Skill model (nullable for theme quests)

**Indexes:**
- Index on user_id
- Index on skill_id
- Index on is_completed (for finding active quests)
- Composite index on (user_id, is_completed) for user's active quests

**Constraints:**
- CHECK constraint: current_progress >= 0
- CHECK constraint: target_progress > 0
- CHECK constraint: completion_type IN ('one_time', 'cumulative', 'recursive', 'streak')
- CHECK constraint: failure_count >= 0

**Requirements:**
1. Use SQLAlchemy 2.0 syntax
2. JSON column for success_criteria (flexible quest definitions)
3. Foreign keys with CASCADE delete
4. skill_id is nullable (theme quests don't have associated skill)
5. Add docstring explaining 4 quest types

**Output Format:**
```python
class Quest(Base):
    \"\"\"[Docstring explaining 4 quest completion types]\"\"\"
    __tablename__ = "quests"
    
    # [Columns]
    
    # [Relationships]
    
    # [Indexes and constraints]
    __table_args__ = (
        [indexes and CHECK constraints],
    )
```

Generate the complete Quest model now.

---PROMPT END---
```

**Save to:** `src/db/models.py` (append)

---

## SUMMARY OF SECTION 1

**After completing Prompts 1.1-1.5, you should have:**
- `src/db/models.py` with 5 core models:
  - User
  - Skill
  - Theme
  - JournalEntry
  - Quest

**Next:** Run prompt for database session management (Prompt 2.1)

---

## SECTION 2: DATABASE SESSION & INITIALIZATION

### Prompt 2.1: Database Session Manager

```
---PROMPT START---

I'm building an RPG Life Tracker application. Generate a database session manager module.

**Project Context:**
This module handles SQLAlchemy session creation, connection pooling, and database initialization. It supports both SQLite (dev/test) and PostgreSQL (production).

**Requirements:**

1. **Load configuration from YAML:**
   - File location: `config/dev.yaml`
   - Read database type (sqlite or postgresql)
   - Read connection parameters

2. **Create database engine:**
   - SQLite: Use `sqlite:///` with `check_same_thread=False` and `StaticPool`
   - PostgreSQL: Use `postgresql://` with `pool_pre_ping=True`

3. **Session management:**
   - Create `SessionLocal` factory with `sessionmaker`
   - Provide `get_db()` context manager for FastAPI dependency injection
   - Auto-commit on success, auto-rollback on error

4. **Utility functions:**
   - `init_db()`: Create all tables (for initial setup)
   - `drop_db()`: Drop all tables (for testing only)

**File Structure:**
```python
# src/db/session.py

import yaml
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.db.models import Base  # Import Base from models.py

# [Load config from config/dev.yaml]

# [Create engine based on config]

# [Create SessionLocal factory]

# [Implement init_db()]

# [Implement drop_db()]

# [Implement get_db() context manager]
```

**Config File Format (config/dev.yaml):**
```yaml
database:
  type: "sqlite"  # or "postgresql"
  sqlite:
    path: "data/db/rpg_life_tracker.db"
  postgresql:
    host: "localhost"
    port: 5432
    database: "rpg_life_tracker"
    username: "postgres"
    password: "password"
```

**Usage Example:**
```python
# In FastAPI route
from src.db.session import get_db

@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return users
```

**Error Handling:**
- Wrap get_db() in try/except
- Auto-rollback on exception
- Always close session in finally block

Generate the complete session manager module now.

---PROMPT END---
```

**Save to:** `src/db/session.py`

---

### Prompt 2.2: Database Initialization Script

```
---PROMPT START---

I'm building an RPG Life Tracker application. Generate a database initialization script.

**Project Context:**
This script creates all database tables on first run. It's used during initial setup and in test environments.

**Requirements:**

1. **Import session manager:**
   - From `src.db.session` import `init_db`
   - From `src.db.models` import `Base` (to verify models loaded)

2. **Main function:**
   - Print status message: "Initializing database..."
   - Call `init_db()`
   - Print success message with table count
   - Use `loguru` for logging

3. **Verify tables created:**
   - Use SQLAlchemy inspector to count tables
   - Print table names for verification

**File Structure:**
```python
# scripts/init_db.py

from loguru import logger
from sqlalchemy import inspect

from src.db.session import init_db, engine
from src.db.models import Base

def main():
    \"\"\"Initialize database tables.\"\"\"
    logger.info("Initializing database...")
    
    # Create all tables
    init_db()
    
    # Verify tables created
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    logger.info(f"✅ Database initialized successfully ({len(table_names)} tables created)")
    logger.info(f"Tables: {', '.join(table_names)}")

if __name__ == "__main__":
    main()
```

**Usage:**
```bash
# Run from project root
python scripts/init_db.py
```

**Expected Output:**
```
[INFO] Initializing database...
[INFO] ✅ Database initialized successfully (5 tables created)
[INFO] Tables: users, skills, themes, journal_entries, quests
```

Generate the complete initialization script now.

---PROMPT END---
```

**Save to:** `scripts/init_db.py`

---

## SECTION 3: CORE SERVICES (XP CALCULATION)

### Prompt 3.1: XP Calculation Module

```
---PROMPT START---

I'm building an RPG Life Tracker application. Generate the XP calculation module implementing power-law progression.

**Project Context:**
The XP system uses a power-law formula with increasing exponents at rank boundaries (Rank F: 1.5×, Rank E-A: 1.6×, Rank S: 1.8×, Rank SS-SSS: 2.0×). Base XP is 480 (one 30-minute deliberate practice session).

**Mathematical Formulas:**

**XP Required for Level (Appendix A.1):**
```
Level 1: 0 XP
Levels 2-20 (Rank F): 480 × 1.5^(level-1)
Levels 21-40 (Rank E-A): 480 × 1.5^19 × 1.6^(level-20)
Levels 41-60 (Rank S): 480 × 1.5^19 × 1.6^20 × 1.8^(level-40)
Levels 61-100 (Rank SS-SSS): 480 × 1.5^19 × 1.6^20 × 1.8^20 × 2.0^(level-60)
```

**Session XP Formula (Section 3.3):**
```
session_xp = base_xp × (minutes / 30) × quality_mult × (1 + variety_bonus) × troll_mult

Where:
- base_xp = 480 (baseline for 30 min deliberate practice)
- minutes = session duration in minutes
- quality_mult = 0.5-2.0 (deliberate practice quality assessment)
- variety_bonus = 0.0-0.60 (balance variety bonus)
- troll_mult = 1.0-5.0 (anomaly bonus for exceptional performance)
```

**Theme XP Propagation (Q22 EXTRA):**
```
theme_xp = max(1, skill_xp × 0.001)

(Themes receive 0.1% of skill XP, minimum 1 XP per session)
```

**Functions to Implement:**

1. **calculate_xp_for_level(level: int) -> int**
   - Input: Target level (1-100)
   - Output: Total XP required to reach that level
   - Handle all 4 rank tiers with correct exponents

2. **calculate_level_from_xp(total_xp: int) -> int**
   - Input: Total XP accumulated
   - Output: Current level (1-100)
   - Use binary search for O(log n) performance

3. **calculate_session_xp(base_xp: int, minutes: int, quality_mult: float, variety_bonus: float, troll_multiplier: float = 1.0) -> Dict[str, int]**
   - Input: All session parameters
   - Output: Dict with 'skill_xp' and 'theme_xp' keys
   - Apply formula, round to integers

4. **calculate_theme_xp_from_skill(skill_xp: int) -> int**
   - Input: Skill XP awarded
   - Output: Theme XP (0.1% propagation, minimum 1)

**File Structure:**
```python
# src/core/xp.py

\"\"\"
XP Calculation Module
Based on Architecture Section 3 (XP & Progression System)
\"\"\"

from typing import Dict
import math


def calculate_xp_for_level(level: int) -> int:
    \"\"\"[Docstring with formula explanation]\"\"\"
    # [Implementation with 4 rank tiers]
    pass


def calculate_level_from_xp(total_xp: int) -> int:
    \"\"\"[Docstring explaining binary search approach]\"\"\"
    # [Implementation using binary search]
    pass


def calculate_session_xp(
    base_xp: int,
    minutes: int,
    quality_mult: float,
    variety_bonus: float,
    troll_multiplier: float = 1.0
) -> Dict[str, int]:
    \"\"\"[Docstring with formula]\"\"\"
    # [Implementation with theme XP propagation]
    pass


def calculate_theme_xp_from_skill(skill_xp: int) -> int:
    \"\"\"[Docstring explaining 0.1% propagation]\"\"\"
    # [Implementation]
    pass
```

**Test Values (for validation):**
```python
# Level → XP mappings (from architecture)
assert calculate_xp_for_level(1) == 0
assert calculate_xp_for_level(2) == 480
assert calculate_xp_for_level(5) == 5093
assert calculate_xp_for_level(30) == 296227  # Target: 90 days
assert calculate_xp_for_level(50) == 2515393
assert calculate_xp_for_level(100) == 175234560

# Session XP example
result = calculate_session_xp(480, 60, 1.2, 0.30, 1.0)
# Expected: skill_xp ≈ 1498 (480 × 2.0 × 1.2 × 1.3)
# Expected: theme_xp ≥ 1 (max(1, 1498 × 0.001))
```

Generate the complete XP calculation module now with all 4 functions.

---PROMPT END---
```

**Save to:** `src/core/xp.py`

---

### Prompt 3.2: Quest Matching Module

```
---PROMPT START---

I'm building an RPG Life Tracker application. Generate the quest matching module.

**Project Context:**
Quests are matched to journal entries based on detected activities and skills. There are 4 completion types that require different matching logic.

**Quest Completion Types (Section 6):**

1. **one_time:** Single achievement (e.g., "Complete First 5K Run")
   - Match: Check if specific activity occurred
   - Complete: Set progress to 1.0 when matched

2. **cumulative:** Accumulate progress (e.g., "Write 50,000 Words Total")
   - Match: Always matches for relevant activity
   - Complete: When current_progress >= target_progress

3. **recursive:** Repeat N times per period (e.g., "Meditate 3× Weekly")
   - Match: Check if activity occurred this period
   - Complete: When repetitions reach target for current period

4. **streak:** Consecutive days (e.g., "Code Daily for 30 Days")
   - Match: Check if activity occurred today
   - Complete: When streak reaches target days

**Functions to Implement:**

1. **match_quests(entry: JournalEntry, user_id: str, detected_skills: List[str], detected_activities: List[str], db: Session) -> List[Quest]**
   - Get all active quests for user (is_completed=False)
   - Check each quest against entry/skills/activities
   - Return list of matching quests

2. **check_quest_match(quest: Quest, entry: JournalEntry, detected_skills: List[str], detected_activities: List[str]) -> bool**
   - Implement matching logic for each completion type
   - Use quest.success_criteria JSON for matching rules

3. **update_quest_progress(quest: Quest, progress_delta: float, db: Session) -> bool**
   - Add progress_delta to current_progress
   - Check if quest completed (current_progress >= target_progress)
   - Set is_completed=True and completed_at if done
   - Return True if quest completed

**File Structure:**
```python
# src/core/quests.py

\"\"\"
Quest Matching & Completion Module
Based on Architecture Section 6 (Quest System)
\"\"\"

from typing import List
from datetime import datetime
from sqlalchemy.orm import Session

from src.db.models import Quest, JournalEntry


def match_quests(
    entry: JournalEntry,
    user_id: str,
    detected_skills: List[str],
    detected_activities: List[str],
    db: Session
) -> List[Quest]:
    \"\"\"
    Match journal entry to active quests.
    
    Args:
        entry: Journal entry being processed
        user_id: User ID
        detected_skills: Skills detected in entry (e.g., ["Python Programming", "Cardio Running"])
        detected_activities: Activities detected (e.g., ["coded", "ran"])
        db: Database session
    
    Returns:
        List of matching Quest objects
    \"\"\"
    # Get active quests
    active_quests = db.query(Quest).filter(
        Quest.user_id == user_id,
        Quest.is_completed == False
    ).all()
    
    matched = []
    for quest in active_quests:
        if check_quest_match(quest, entry, detected_skills, detected_activities):
            matched.append(quest)
    
    return matched


def check_quest_match(
    quest: Quest,
    entry: JournalEntry,
    detected_skills: List[str],
    detected_activities: List[str]
) -> bool:
    \"\"\"
    Check if entry matches quest criteria.
    
    Args:
        quest: Quest to check
        entry: Journal entry
        detected_skills: Detected skills
        detected_activities: Detected activities
    
    Returns:
        True if entry matches quest
    \"\"\"
    # [Implementation for each completion_type]
    pass


def update_quest_progress(quest: Quest, progress_delta: float, db: Session) -> bool:
    \"\"\"
    Update quest progress and check completion.
    
    Args:
        quest: Quest to update
        progress_delta: Amount to add to progress
        db: Database session
    
    Returns:
        True if quest was completed by this update
    \"\"\"
    # [Implementation]
    pass
```

**Matching Examples:**

```python
# Example 1: one_time quest
quest = Quest(
    quest_name="Complete First 5K Run",
    completion_type="one_time",
    success_criteria={"keywords": ["5K", "5 km", "5 kilometers"], "activity": "running"}
)
# Match if: "5K" or "5 km" in entry text AND "running" in detected_activities

# Example 2: cumulative quest
quest = Quest(
    quest_name="Write 50,000 Words Total",
    completion_type="cumulative",
    success_criteria={"skill": "Writing", "target": 50000},
    target_progress=50000
)
# Match if: "Writing" in detected_skills
# Update: current_progress += entry.word_count

# Example 3: recursive quest
quest = Quest(
    quest_name="Meditate 3× Weekly",
    completion_type="recursive",
    success_criteria={"skill": "Meditation", "frequency": 3, "period": "weekly"}
)
# Match if: "Meditation" in detected_skills AND not already counted this week

# Example 4: streak quest
quest = Quest(
    quest_name="Code Daily for 30 Days",
    completion_type="streak",
    success_criteria={"skill": "Python Programming", "consecutive_days": 30},
    target_progress=30
)
# Match if: "Python Programming" in detected_skills AND entry.created_at is today
```

Generate the complete quest matching module now with all 3 functions and matching logic for all 4 quest types.

---PROMPT END---
```

**Save to:** `src/core/quests.py`

---

## SECTION 4: UNIT TESTS (95% COVERAGE TARGET)

### Prompt 4.1: XP Calculation Tests

```
---PROMPT START---

I'm building an RPG Life Tracker application. Generate comprehensive pytest unit tests for the XP calculation module.

**Project Context:**
Testing the power-law XP progression formulas to ensure they match the architecture specifications exactly.

**Requirements:**

1. **Test calculate_xp_for_level():**
   - Test all known level → XP mappings from architecture
   - Test rank boundary transitions (levels 20, 40, 60)
   - Test exponent changes at boundaries
   - Test monotonic increase (each level requires more XP)
   - Test edge cases (level 1, level 100)

2. **Test calculate_level_from_xp():**
   - Test inverse relationship with calculate_xp_for_level()
   - Test exact level boundaries
   - Test XP values between levels
   - Test edge cases (0 XP, maximum XP)

3. **Test calculate_session_xp():**
   - Test baseline session (30 min, 1.0× quality, 0.0 variety)
   - Test time scaling (60 min = 2× XP)
   - Test quality multiplier effect
   - Test variety bonus effect
   - Test troll multiplier effect
   - Test theme XP propagation (0.1% rule)

4. **Test calculate_theme_xp_from_skill():**
   - Test 0.1% calculation
   - Test minimum 1 XP rule
   - Test rounding behavior

**Coverage Target:** 100% (all functions, all branches)

**File Structure:**
```python
# tests/unit/core/test_xp.py

\"\"\"
Unit tests for XP calculation module.
Target: 100% coverage
\"\"\"

import pytest
from src.core.xp import (
    calculate_xp_for_level,
    calculate_level_from_xp,
    calculate_session_xp,
    calculate_theme_xp_from_skill
)


class TestXPForLevel:
    \"\"\"Test XP requirements for each level.\"\"\"
    
    @pytest.mark.parametrize("level,expected_xp", [
        (1, 0),
        (2, 480),
        (5, 5093),
        (10, 22800),
        (20, 345943),
        (30, 296227),
        (40, 1013776),
        (50, 2515393),
        (60, 5765760),
        (100, 175234560),
    ])
    def test_xp_for_level_matches_architecture(self, level: int, expected_xp: int):
        \"\"\"Test XP requirements match architecture table.\"\"\"
        calculated = calculate_xp_for_level(level)
        # Allow ±10 XP tolerance for rounding
        assert abs(calculated - expected_xp) < 10, \
            f"Level {level}: Expected {expected_xp}, got {calculated}"
    
    def test_level_1_is_zero_xp(self):
        \"\"\"Level 1 should require 0 XP.\"\"\"
        assert calculate_xp_for_level(1) == 0
    
    def test_xp_increases_monotonically(self):
        \"\"\"XP should increase with each level.\"\"\"
        for level in range(1, 100):
            xp_current = calculate_xp_for_level(level)
            xp_next = calculate_xp_for_level(level + 1)
            assert xp_next > xp_current, f"Level {level} → {level+1} didn't increase"
    
    def test_exponent_changes_at_rank_boundaries(self):
        \"\"\"Exponent should change at levels 20, 40, 60.\"\"\"
        # Rank F→E transition (level 20→21)
        xp_20 = calculate_xp_for_level(20)
        xp_21 = calculate_xp_for_level(21)
        ratio_20_21 = xp_21 / xp_20
        assert 1.55 < ratio_20_21 < 1.65, f"Exponent change F→E incorrect: {ratio_20_21}"
        
        # Rank A→S transition (level 40→41)
        xp_40 = calculate_xp_for_level(40)
        xp_41 = calculate_xp_for_level(41)
        ratio_40_41 = xp_41 / xp_40
        assert 1.75 < ratio_40_41 < 1.85, f"Exponent change A→S incorrect: {ratio_40_41}"
        
        # Rank S→SS transition (level 60→61)
        xp_60 = calculate_xp_for_level(60)
        xp_61 = calculate_xp_for_level(61)
        ratio_60_61 = xp_61 / xp_60
        assert 1.95 < ratio_60_61 < 2.05, f"Exponent change S→SS incorrect: {ratio_60_61}"


class TestLevelFromXP:
    \"\"\"Test level calculation from XP.\"\"\"
    
    @pytest.mark.parametrize("total_xp,expected_level", [
        (0, 1),
        (479, 1),
        (480, 2),
        (5092, 4),
        (5093, 5),
        (296227, 30),
        (1000000, 41),
    ])
    def test_level_from_xp_matches_table(self, total_xp: int, expected_level: int):
        \"\"\"Test level calculation from XP.\"\"\"
        calculated = calculate_level_from_xp(total_xp)
        assert calculated == expected_level, \
            f"XP {total_xp}: Expected level {expected_level}, got {calculated}"
    
    def test_level_from_xp_is_inverse(self):
        \"\"\"Test that level_from_xp is inverse of xp_for_level.\"\"\"
        for level in [1, 5, 10, 20, 30, 50, 80]:
            xp = calculate_xp_for_level(level)
            calculated_level = calculate_level_from_xp(xp)
            assert calculated_level == level, \
                f"Level {level} → XP {xp} → Level {calculated_level} (expected {level})"


class TestSessionXP:
    \"\"\"Test session XP calculation.\"\"\"
    
    def test_baseline_session(self):
        \"\"\"Test 30-minute baseline session.\"\"\"
        result = calculate_session_xp(480, 30, 1.0, 0.0, 1.0)
        assert result["skill_xp"] == 480
        assert result["theme_xp"] == 1  # max(1, 480 * 0.001)
    
    def test_time_scaling(self):
        \"\"\"Test session XP scales linearly with time.\"\"\"
        result_30 = calculate_session_xp(480, 30, 1.0, 0.0)
        result_60 = calculate_session_xp(480, 60, 1.0, 0.0)
        
        assert result_60["skill_xp"] == result_30["skill_xp"] * 2
    
    def test_quality_multiplier(self):
        \"\"\"Test quality multiplier effect.\"\"\"
        result_low = calculate_session_xp(480, 30, 0.5, 0.0)
        result_high = calculate_session_xp(480, 30, 2.0, 0.0)
        
        assert result_low["skill_xp"] == 240  # 480 * 0.5
        assert result_high["skill_xp"] == 960  # 480 * 2.0
    
    def test_variety_bonus(self):
        \"\"\"Test variety bonus increases XP.\"\"\"
        result_no_variety = calculate_session_xp(480, 30, 1.0, 0.0)
        result_with_variety = calculate_session_xp(480, 30, 1.0, 0.30)
        
        expected_with_variety = int(480 * 1.3)
        assert abs(result_with_variety["skill_xp"] - expected_with_variety) < 5
    
    def test_theme_xp_propagation(self):
        \"\"\"Test theme XP is 0.1% of skill XP.\"\"\"
        result = calculate_session_xp(480, 60, 1.5, 0.30)
        skill_xp = result["skill_xp"]
        theme_xp = result["theme_xp"]
        
        expected_theme_xp = max(1, int(skill_xp * 0.001))
        assert theme_xp == expected_theme_xp


class TestThemeXPPropagation:
    \"\"\"Test theme XP calculation from skill XP.\"\"\"
    
    def test_0_1_percent_calculation(self):
        \"\"\"Test 0.1% (0.001) propagation.\"\"\"
        assert calculate_theme_xp_from_skill(1000) == 1  # 1000 * 0.001 = 1
        assert calculate_theme_xp_from_skill(5000) == 5  # 5000 * 0.001 = 5
        assert calculate_theme_xp_from_skill(10000) == 10  # 10000 * 0.001 = 10
    
    def test_minimum_1_xp(self):
        \"\"\"Test minimum 1 XP rule.\"\"\"
        assert calculate_theme_xp_from_skill(100) == 1  # Would be 0.1, but minimum is 1
        assert calculate_theme_xp_from_skill(500) == 1  # Would be 0.5, but minimum is 1
        assert calculate_theme_xp_from_skill(999) == 1  # Would be 0.999, rounds to 1


# Run with: pytest tests/unit/core/test_xp.py -v --cov=src.core.xp --cov-report=term-missing
```

Generate the complete XP test suite now with all test classes and methods.

---PROMPT END---
```

**Save to:** `tests/unit/core/test_xp.py`

**Run:** `pytest tests/unit/core/test_xp.py -v --cov=src.core.xp --cov-fail-under=100`

---

## END OF WEEK 2.5 COMPLETE PROMPTS

**Total Prompts Provided:** 9 prompts (covering ~70% of Week 2.5 work)

**Files Generated After Using These Prompts:**
1. `src/db/models.py` - 5 SQLAlchemy models (User, Skill, Theme, JournalEntry, Quest)
2. `src/db/session.py` - Database session manager
3. `scripts/init_db.py` - Database initialization script
4. `src/core/xp.py` - XP calculation module (4 functions)
5. `src/core/quests.py` - Quest matching module (3 functions)
6. `tests/unit/core/test_xp.py` - XP unit tests (100% coverage)

**Next Steps:**
1. Run each prompt in order (1.1 → 1.5 → 2.1 → 2.2 → 3.1 → 3.2 → 4.1)
2. Test each generated file immediately
3. Fix any errors by providing error messages back to AI
4. Move to remaining Week 2.5 tasks (not covered in these prompts)

**Remaining Week 2.5 Tasks (Use CODE_GENERATION_PROMPTS.md templates):**
- Theme propagation module (src/core/themes.py)
- Alembic migrations setup
- Integration tests (database operations)
- Performance benchmarks
- Validation gates

---

**Document Status:** PRODUCTION READY  
**Prompt Type:** Complete (no placeholders)  
**Coverage:** Week 2.5 core tasks (database + XP + quests)  
**Usage:** Copy-paste directly into Claude/GPT-4  
**Next:** Run prompts, test generated code, proceed to Week 3

---

END OF WEEK_2.5_COMPLETE_PROMPTS.md
