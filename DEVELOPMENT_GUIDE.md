# DEVELOPMENT GUIDE: MVP Implementation Roadmap
## "Life Sucks But You Got a Status Window Now" - 6-Week Sprint

**Target Completion:** Mid-March 2026  
**Total Duration:** 6 weeks (42 days)  
**Developer:** Sebastian (with AI assistance: Copilot + Claude Code)  
**Methodology:** Agile sprints, iterative development, test early & often

---

## 🗺️ HIGH-LEVEL ROADMAP

```
Week 1: Foundation & Database
Week 2: Core Game Logic (XP, Skills, Titles)
Week 3: AI Integration (Categorization)
Week 4: Missions/Quests System
Week 5: Frontend Dashboard
Week 6: Polish, Testing, Voice Input (Stretch)
```

---

## WEEK 1: FOUNDATION & DATABASE SETUP

### **Goal:** Establish project structure, database schema, and basic CRUD operations

### Day 1-2: Project Initialization
**Tasks:**
1. ✅ Clone/restructure existing repo
2. ✅ Create virtual environment
3. ✅ Install dependencies
4. ✅ Set up FastAPI skeleton
5. ✅ Configure Ollama connection

**Deliverables:**
```bash
# File: requirements.txt
fastapi==0.128.0
uvicorn[standard]==0.40.0
sqlalchemy==2.0.46  # Using SQLAlchemy 2.0 typed ORM with Mapped/mapped_column
alembic==1.18.3
pydantic==2.12.5
python-dotenv==1.2.1
ollama==0.1.6  # Python client for Ollama
pytest==7.4.4
pytest-cov==3.0.0
```

```python
# File: app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Status Window API",
    description="Gamified life-tracking system for neurodivergent users",
    version="0.1.0"
)

# CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "Status Window API v0.1.0",
        "docs": "/docs",
        "health": "OK"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "ollama_connected": check_ollama()}

def check_ollama():
    try:
        import ollama
        ollama.list()  # Test connection
        return True
    except:
        return False

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
```

**Checkpoint:** Run `uvicorn app.main:app --reload` and visit `http://localhost:8000/docs` to see Swagger UI

---

### Day 3-4: Database Models
**Tasks:**
1. ✅ Design SQLAlchemy models for all core entities
2. ✅ Create Alembic migrations
3. ✅ Initialize database with sample data

**Deliverables:**

```python
# File: app/models/user.py
# Using SQLAlchemy 2.0 Typed ORM with Mapped and mapped_column
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base

class User(Base):
    __tablename__ = "users"
    
    # Primary key with typed annotation
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Typed relationships - full static type checking support
    themes: Mapped[list["Theme"]] = relationship("Theme", back_populates="user", cascade="all, delete-orphan")
    skills: Mapped[list["Skill"]] = relationship("Skill", back_populates="user", cascade="all, delete-orphan")
    journal_entries: Mapped[list["JournalEntry"]] = relationship("JournalEntry", back_populates="user", cascade="all, delete-orphan")
    user_titles: Mapped[list["UserTitle"]] = relationship("UserTitle", back_populates="user", cascade="all, delete-orphan")
    user_mq: Mapped[list["UserMissionQuest"]] = relationship("UserMissionQuest", back_populates="user", cascade="all, delete-orphan")
    stats: Mapped[Optional["UserStats"]] = relationship("UserStats", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<User {self.username}>"
```

```python
# File: app/models/theme.py
# Using SQLAlchemy 2.0 Typed ORM
import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base

if TYPE_CHECKING:
    from app.models.skill import Skill
    from app.models.user import User

class Theme(Base):
    __tablename__ = "themes"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    xp_to_next_level: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    corrosion_level: Mapped[str] = mapped_column(String(20), default="Fresh", nullable=False)
    parent_theme_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("themes.id"), nullable=True)
    theme_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # Typed relationships with proper back_populates
    user: Mapped["User"] = relationship("User", back_populates="themes")
    parent_theme: Mapped[Optional["Theme"]] = relationship("Theme", remote_side="Theme.id", back_populates="sub_themes")
    sub_themes: Mapped[list["Theme"]] = relationship("Theme", back_populates="parent_theme")
    skills: Mapped[list["Skill"]] = relationship("Skill", back_populates="theme")
    
    def add_xp(self, amount: float) -> None:
        """Add XP and handle level-ups"""
        self.xp += amount
        while self.xp >= self.xp_to_next_level:
            self.level_up()
    
    def level_up(self) -> None:
        self.xp -= self.xp_to_next_level
        self.level += 1
        self.xp_to_next_level = self.calculate_next_level_xp()
    
    def calculate_next_level_xp(self) -> float:
        """Exponential XP scaling"""
        return 100 * (1.15 ** self.level)
```

```python
# File: app/models/skill.py
# Using SQLAlchemy 2.0 Typed ORM
import uuid
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base

if TYPE_CHECKING:
    from app.models.theme import Theme
    from app.models.user import User

class Skill(Base):
    __tablename__ = "skills"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    theme_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("themes.id"), nullable=True)
    parent_skill_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("skills.id"), nullable=True)
    
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    xp_to_next_level: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)
    rank: Mapped[str] = mapped_column(String(20), default="Beginner", nullable=False)
    practice_time_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), default="Medium", nullable=False)
    skill_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # Typed relationships
    user: Mapped["User"] = relationship("User", back_populates="skills")
    theme: Mapped[Optional["Theme"]] = relationship("Theme", back_populates="skills")
    parent_skill: Mapped[Optional["Skill"]] = relationship("Skill", remote_side="Skill.id", back_populates="child_skills")
    child_skills: Mapped[list["Skill"]] = relationship("Skill", back_populates="parent_skill")
    
    def add_practice_time(self, minutes: int, xp_multiplier: float = 1.0) -> None:
        """Log practice time and award XP"""
        self.practice_time_minutes += minutes
        xp_gained = minutes * 0.5 * xp_multiplier  # Base: 0.5 XP per minute
        self.add_xp(xp_gained)
    
    def add_xp(self, amount: float) -> None:
        self.xp += amount
        while self.xp >= self.xp_to_next_level:
            self.level_up()
    
    def level_up(self) -> None:
        self.xp -= self.xp_to_next_level
        self.level += 1
        self.xp_to_next_level = 50 * (1.2 ** self.level)
        self.update_rank()
    
    def update_rank(self) -> None:
        """Update rank based on level"""
        if self.level < 5:
            self.rank = "Beginner"
        elif self.level < 15:
            self.rank = "Amateur"
        elif self.level < 30:
            self.rank = "Intermediate"
        elif self.level < 50:
            self.rank = "Advanced"
        elif self.level < 80:
            self.rank = "Expert"
        else:
            self.rank = "Master"
```

```python
# File: app/models/title.py
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, JSON, DateTime, Table
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.utils.database import Base

# Global Title Bank (shared across users)
class TitleTemplate(Base):
    __tablename__ = "title_templates"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)
    description_template = Column(String)  # Template with {user_name} placeholders
    effect = Column(JSON, nullable=False)  # {"xp_multiplier": {"theme": "Education", "value": 1.10}}
    rank = Column(String, default="D")  # F, E, D, C, B, A, S
    unlock_condition = Column(JSON, nullable=False)  # {"type": "journal_streak", "value": 7}
    category = Column(String)  # "Social", "Productivity", "Health", etc.
    is_hidden = Column(Boolean, default=False)  # Hidden until unlocked
    
    # Relationships
    user_titles = relationship("UserTitle", back_populates="title_template")

# User-specific title instances
class UserTitle(Base):
    __tablename__ = "user_titles"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title_template_id = Column(String, ForeignKey("title_templates.id"), nullable=False)
    
    acquired_at = Column(DateTime, default=datetime.utcnow)
    is_equipped = Column(Boolean, default=True)  # Can equip/unequip for passive effects
    personalized_description = Column(String)  # AI-generated for this user
    expires_at = Column(DateTime, nullable=True)  # For temporary titles
    
    # Relationships
    user = relationship("User", back_populates="user_titles")
    title_template = relationship("TitleTemplate", back_populates="user_titles")
```

```python
# File: app/models/journal_entry.py
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.utils.database import Base

class JournalEntry(Base):
    __tablename__ = "journal_entries"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    content = Column(Text, nullable=False)
    entry_type = Column(String, default="text")  # text, voice_transcription, file_upload
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # AI-generated fields
    ai_categories = Column(JSON, default={})  # {"themes": [...], "skills": [...], "sentiment": "positive"}
    ai_suggested_quests = Column(JSON, default=[])
    ai_processed = Column(Boolean, default=False)
    
    # Manual categorization (fallback)
    manual_theme_ids = Column(JSON, default=[])
    manual_skill_ids = Column(JSON, default=[])
    
    # Relationships
    user = relationship("User", back_populates="journal_entries")
```

**Checkpoint:** Run `alembic revision --autogenerate -m "Initial models"` and `alembic upgrade head`

---

### Day 5: CRUD Operations
**Tasks:**
1. ✅ Implement CRUD functions for User, Theme, Skill, Title
2. ✅ Test database operations with pytest

**Deliverables:**

```python
# File: app/crud/user.py
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.user import UserCreate

def create_user(db: Session, user: UserCreate) -> User:
    db_user = User(
        username=user.username,
        email=user.email
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

def get_user(db: Session, user_id: str):
    return db.query(User).filter(User.id == user_id).first()
```

```python
# File: app/crud/theme.py
from sqlalchemy.orm import Session
from app.models.theme import Theme

def create_theme(db: Session, user_id: str, name: str, description: str = ""):
    theme = Theme(user_id=user_id, name=name, description=description)
    db.add(theme)
    db.commit()
    db.refresh(theme)
    return theme

def get_user_themes(db: Session, user_id: str):
    return db.query(Theme).filter(Theme.user_id == user_id).all()

def add_xp_to_theme(db: Session, theme_id: str, xp_amount: float):
    theme = db.query(Theme).filter(Theme.id == theme_id).first()
    if theme:
        theme.add_xp(xp_amount)
        db.commit()
        db.refresh(theme)
    return theme
```

**Checkpoint:** Write and run unit tests for CRUD operations

---

## WEEK 2: CORE GAME LOGIC

### **Goal:** Implement XP calculation, leveling, and Title awarding

### Day 6-7: XP Calculator
**Tasks:**
1. ✅ Build XP distribution engine
2. ✅ Implement level-up logic with exponential scaling
3. ✅ Create XP multiplier system (based on Titles)

**Deliverables:**

```python
# File: app/core/xp_calculator.py
from typing import Dict, List
from sqlalchemy.orm import Session
from app.models.theme import Theme
from app.models.skill import Skill
from app.models.title import UserTitle

class XPCalculator:
    """Handles all XP distribution and level-up logic"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def distribute_journal_xp(
        self, 
        user_id: str, 
        theme_ids: List[str], 
        skill_practice: Dict[str, int]  # {skill_id: minutes}
    ):
        """
        Distribute XP from a journal entry
        
        Args:
            user_id: User ID
            theme_ids: List of theme IDs mentioned in entry
            skill_practice: Dict of {skill_id: practice_minutes}
        """
        # Get user's active title multipliers
        multipliers = self._get_xp_multipliers(user_id)
        
        # Award theme XP (10 XP base per mention)
        for theme_id in theme_ids:
            theme = self.db.query(Theme).filter(Theme.id == theme_id).first()
            if theme:
                base_xp = 10.0
                multiplier = multipliers.get(f"theme_{theme.name}", 1.0)
                theme.add_xp(base_xp * multiplier)
        
        # Award skill XP (practice time-based)
        for skill_id, minutes in skill_practice.items():
            skill = self.db.query(Skill).filter(Skill.id == skill_id).first()
            if skill:
                multiplier = multipliers.get(f"skill_{skill.name}", 1.0)
                skill.add_practice_time(minutes, xp_multiplier=multiplier)
        
        self.db.commit()
    
    def _get_xp_multipliers(self, user_id: str) -> Dict[str, float]:
        """Extract XP multipliers from user's equipped titles"""
        multipliers = {}
        
        user_titles = self.db.query(UserTitle).filter(
            UserTitle.user_id == user_id,
            UserTitle.is_equipped == True
        ).all()
        
        for ut in user_titles:
            effect = ut.title_template.effect
            if effect.get("type") == "xp_multiplier":
                key = f"{effect['scope']}_{effect['target']}"  # e.g., "theme_Education"
                multipliers[key] = effect.get("value", 1.0)
        
        return multipliers
```

**Checkpoint:** Test XP distribution with sample data, verify level-ups occur correctly

---

### Day 8-9: Title Awarding System
**Tasks:**
1. ✅ Implement title unlock condition detection
2. ✅ Create AI-powered personalized title award messages
3. ✅ Seed GlobalTitleBank with 10-15 starter titles

**Deliverables:**

```python
# File: app/core/title_awarder.py
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.title import TitleTemplate, UserTitle
from app.models.journal_entry import JournalEntry
from app.ai.title_generator import generate_personalized_title_message
from datetime import datetime, timedelta

class TitleAwarder:
    """Detects unlock conditions and awards titles"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def check_and_award_titles(self, user_id: str):
        """
        Check all title unlock conditions for a user
        Called after each journal entry or significant action
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        all_title_templates = self.db.query(TitleTemplate).all()
        
        newly_awarded = []
        for template in all_title_templates:
            # Skip if user already has this title
            existing = self.db.query(UserTitle).filter(
                UserTitle.user_id == user_id,
                UserTitle.title_template_id == template.id
            ).first()
            if existing:
                continue
            
            # Check unlock condition
            if self._check_condition(user, template.unlock_condition):
                # Award title
                personalized_msg = generate_personalized_title_message(
                    title_name=template.name,
                    user_name=user.username,
                    unlock_condition=template.unlock_condition
                )
                
                user_title = UserTitle(
                    user_id=user_id,
                    title_template_id=template.id,
                    personalized_description=personalized_msg
                )
                self.db.add(user_title)
                newly_awarded.append(template.name)
        
        self.db.commit()
        return newly_awarded
    
    def _check_condition(self, user: User, condition: dict) -> bool:
        """Evaluate if unlock condition is met"""
        cond_type = condition.get("type")
        
        if cond_type == "journal_streak":
            required_days = condition.get("value", 7)
            return self._check_journal_streak(user.id, required_days)
        
        elif cond_type == "theme_level":
            theme_name = condition.get("theme")
            required_level = condition.get("value", 10)
            theme = self.db.query(Theme).filter(
                Theme.user_id == user.id,
                Theme.name == theme_name
            ).first()
            return theme and theme.level >= required_level
        
        elif cond_type == "total_journal_entries":
            required_count = condition.get("value", 30)
            count = self.db.query(JournalEntry).filter(
                JournalEntry.user_id == user.id
            ).count()
            return count >= required_count
        
        # Add more condition types as needed
        return False
    
    def _check_journal_streak(self, user_id: str, required_days: int) -> bool:
        """Check if user has consecutive journaling streak"""
        entries = self.db.query(JournalEntry).filter(
            JournalEntry.user_id == user_id
        ).order_by(JournalEntry.created_at.desc()).all()
        
        if not entries:
            return False
        
        # Check consecutive days
        streak = 1
        current_date = entries[0].created_at.date()
        
        for i in range(1, len(entries)):
            prev_date = entries[i].created_at.date()
            if (current_date - prev_date).days == 1:
                streak += 1
                current_date = prev_date
            else:
                break
        
        return streak >= required_days
```

```python
# File: scripts/seed_global_elements.py
"""Seed GlobalTitleBank with starter titles"""
from app.utils.database import SessionLocal
from app.models.title import TitleTemplate

def seed_titles():
    db = SessionLocal()
    
    titles = [
        {
            "name": "Consistent Chronicler",
            "description_template": "{user_name}, your dedication to daily reflection has earned you the 'Consistent Chronicler' title. Your 7-day streak shows commitment to self-awareness.",
            "effect": {"type": "xp_multiplier", "scope": "theme", "target": "Education", "value": 1.10},
            "rank": "C",
            "unlock_condition": {"type": "journal_streak", "value": 7},
            "category": "Productivity"
        },
        {
            "name": "Early Riser",
            "description_template": "The early bird catches the worm, {user_name}! Your morning journal entries have unlocked the 'Early Riser' title.",
            "effect": {"type": "difficulty_modifier", "scope": "time", "target": "morning", "value": -0.10},
            "rank": "D",
            "unlock_condition": {"type": "morning_journal_count", "value": 10},
            "category": "Lifestyle"
        },
        {
            "name": "Night Owl",
            "description_template": "Burning the midnight oil, {user_name}? Your late-night entries have earned you the 'Night Owl' title.",
            "effect": {"type": "difficulty_modifier", "scope": "time", "target": "morning", "value": 0.10},
            "rank": "D",
            "unlock_condition": {"type": "late_night_journal_count", "value": 10},
            "category": "Lifestyle"
        },
        # Add 10+ more titles...
    ]
    
    for title_data in titles:
        existing = db.query(TitleTemplate).filter(
            TitleTemplate.name == title_data["name"]
        ).first()
        if not existing:
            title = TitleTemplate(**title_data)
            db.add(title)
    
    db.commit()
    print(f"Seeded {len(titles)} title templates")
    db.close()

if __name__ == "__main__":
    seed_titles()
```

**Checkpoint:** Award a title manually, verify it shows up in user's title list with personalized message

---

## WEEK 3: AI INTEGRATION

### **Goal:** Integrate Ollama for journal categorization and quest suggestions

### Day 10-12: Ollama Client & Categorizer
**Tasks:**
1. ✅ Build Ollama Python client wrapper
2. ✅ Create prompt templates for categorization
3. ✅ Implement journal entry AI processing

**Deliverables:**

```python
# File: app/ai/ollama_client.py
import ollama
from typing import Dict, Any
import json

class OllamaClient:
    """Wrapper for Ollama API calls"""
    
    def __init__(self, model: str = "llama3.2"):
        self.model = model
        self._check_connection()
    
    def _check_connection(self):
        """Verify Ollama is running and model is available"""
        try:
            models = ollama.list()
            if self.model not in [m['name'] for m in models['models']]:
                print(f"Warning: {self.model} not found. Run: ollama pull {self.model}")
        except Exception as e:
            raise ConnectionError(f"Cannot connect to Ollama: {e}")
    
    def generate(self, prompt: str, system: str = "", temperature: float = 0.7) -> str:
        """Generate completion from Ollama"""
        response = ollama.generate(
            model=self.model,
            prompt=prompt,
            system=system,
            options={"temperature": temperature}
        )
        return response['response']
    
    def generate_json(self, prompt: str, system: str = "") -> Dict[str, Any]:
        """Generate JSON response (for structured outputs)"""
        response_text = self.generate(prompt, system, temperature=0.3)
        
        # Extract JSON from response (sometimes wrapped in markdown)
        try:
            # Try direct parse
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try extracting from markdown code block
            import re
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            else:
                raise ValueError(f"Could not parse JSON from: {response_text}")
```

```python
# File: app/ai/categorizer.py
from typing import Dict, List
from app.ai.ollama_client import OllamaClient
from app.ai.prompts import CATEGORIZATION_PROMPT

class JournalCategorizer:
    """AI-powered journal entry categorization"""
    
    def __init__(self):
        self.client = OllamaClient(model="llama3.2")
    
    def categorize_entry(
        self,
        entry_text: str,
        user_themes: List[Dict],
        user_skills: List[Dict],
        active_mq: List[Dict]
    ) -> Dict:
        """
        Categorize a journal entry using AI
        
        Returns:
        {
            "themes": [theme_id1, theme_id2],
            "skills": [{"skill_id": "uuid", "practice_minutes": 30}],
            "completed_mq": [mq_id1],
            "sentiment": "positive",
            "suggested_quests": [...]
        }
        """
        # Build context
        theme_context = "\n".join([f"- {t['name']} (ID: {t['id']})" for t in user_themes])
        skill_context = "\n".join([f"- {s['name']} (ID: {s['id']})" for s in user_skills])
        mq_context = "\n".join([f"- {m['name']} (ID: {m['id']})" for m in active_mq])
        
        # Fill prompt template
        prompt = CATEGORIZATION_PROMPT.format(
            entry_text=entry_text,
            user_themes=theme_context,
            user_skills=skill_context,
            active_mq=mq_context
        )
        
        # Call AI
        try:
            result = self.client.generate_json(prompt)
            return result
        except Exception as e:
            print(f"AI categorization failed: {e}")
            # Fallback: return empty categorization
            return {
                "themes": [],
                "skills": [],
                "completed_mq": [],
                "sentiment": "neutral",
                "suggested_quests": []
            }
```

```python
# File: app/ai/prompts.py
CATEGORIZATION_PROMPT = """
You are analyzing a journal entry for a gamified life-tracking app designed for neurodivergent users.

USER'S ACTIVE THEMES:
{user_themes}

USER'S SKILLS:
{user_skills}

ACTIVE MISSIONS/QUESTS:
{active_mq}

JOURNAL ENTRY:
"{entry_text}"

YOUR TASK:
1. Identify which Themes this entry relates to (return theme IDs)
2. Identify which Skills were practiced (estimate practice time in minutes)
3. Check if this entry completes any active Missions/Quests (return M/Q IDs if completed)
4. Analyze sentiment: Positive, Neutral, or Negative
5. Suggest 1-3 new Quest ideas based on this entry

IMPORTANT:
- Be generous with categorization (neurodivergent users benefit from seeing progress)
- Even small activities count (e.g., "thought about coding" = 5 minutes practice)
- Sentiment should be empathetic, not clinical

RETURN ONLY VALID JSON (no markdown, no explanations):
{{
  "themes": ["theme_id1", "theme_id2"],
  "skills": [
    {{"skill_id": "uuid", "practice_minutes": 30}}
  ],
  "completed_mq": ["mq_id1"],
  "sentiment": "positive",
  "suggested_quests": [
    {{"name": "Quest name", "description": "Description", "theme_id": "theme_id"}}
  ]
}}
"""
```

**Checkpoint:** Test categorizer with sample journal entries, verify JSON output is valid

---

### Day 13-14: AI Processing Pipeline
**Tasks:**
1. ✅ Integrate categorizer into journal entry API
2. ✅ Implement automatic XP distribution after AI processing
3. ✅ Add error handling and fallbacks

**Deliverables:**

```python
# File: app/api/v1/journal.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.utils.database import get_db
from app.schemas.journal import JournalEntryCreate, JournalEntryResponse
from app.models.journal_entry import JournalEntry
from app.ai.categorizer import JournalCategorizer
from app.core.xp_calculator import XPCalculator
from app.core.title_awarder import TitleAwarder

router = APIRouter(prefix="/journal", tags=["journal"])

@router.post("/entry", response_model=JournalEntryResponse)
async def create_journal_entry(
    entry: JournalEntryCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new journal entry and process it with AI
    
    Flow:
    1. Save entry to database
    2. Run AI categorization
    3. Distribute XP to themes/skills
    4. Check for title unlocks
    5. Return entry with AI suggestions
    """
    # Create entry
    db_entry = JournalEntry(
        user_id=entry.user_id,
        content=entry.content,
        entry_type="text"
    )
    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)
    
    # Get user context for AI
    user_themes = [{"id": t.id, "name": t.name} for t in db_entry.user.themes]
    user_skills = [{"id": s.id, "name": s.name} for s in db_entry.user.skills]
    active_mq = []  # TODO: Fetch active M/Q
    
    # Run AI categorization
    categorizer = JournalCategorizer()
    ai_result = categorizer.categorize_entry(
        entry_text=entry.content,
        user_themes=user_themes,
        user_skills=user_skills,
        active_mq=active_mq
    )
    
    # Save AI results
    db_entry.ai_categories = ai_result
    db_entry.ai_processed = True
    
    # Distribute XP
    xp_calc = XPCalculator(db)
    skill_practice = {s["skill_id"]: s["practice_minutes"] for s in ai_result["skills"]}
    xp_calc.distribute_journal_xp(
        user_id=entry.user_id,
        theme_ids=ai_result["themes"],
        skill_practice=skill_practice
    )
    
    # Check for title unlocks
    title_awarder = TitleAwarder(db)
    newly_awarded_titles = title_awarder.check_and_award_titles(entry.user_id)
    
    db.commit()
    
    return {
        "id": db_entry.id,
        "content": db_entry.content,
        "ai_categories": ai_result,
        "newly_awarded_titles": newly_awarded_titles,
        "message": f"Entry saved! +{len(ai_result['themes'])} theme XP, +{len(ai_result['skills'])} skill practice logged."
    }
```

**Checkpoint:** POST a journal entry via `/journal/entry`, verify XP is distributed and titles are awarded

---

## WEEK 4: MISSIONS/QUESTS SYSTEM

### **Goal:** Implement M/Q creation, tracking, and completion

### Day 15-17: M/Q Models & CRUD
**Tasks:**
1. ✅ Create MissionQuest model with hierarchy support
2. ✅ Implement M/Q creation, retrieval, update, delete
3. ✅ Build quest matcher (match journal entries to active M/Q)

**Deliverables:**

```python
# File: app/models/mission_quest.py
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.utils.database import Base

class MissionQuestTemplate(Base):
    """Global M/Q bank (reusable templates)"""
    __tablename__ = "mq_templates"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description_template = Column(String)
    type = Column(String)  # daily, timed, periodic, repeatable, etc.
    structure = Column(String)  # single_action, multi_action, multi_part
    completion_condition = Column(JSON)  # {"type": "yes_no"} or {"type": "accumulation", "target": 50}
    reward_xp = Column(Integer, default=0)
    reward_coins = Column(Integer, default=0)
    difficulty = Column(String, default="medium")
    category = Column(String)
    
    user_mq = relationship("UserMissionQuest", back_populates="template")

class UserMissionQuest(Base):
    """User-specific M/Q instances"""
    __tablename__ = "user_mq"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    template_id = Column(String, ForeignKey("mq_templates.id"), nullable=True)
    parent_mq_id = Column(String, ForeignKey("user_mq.id"), nullable=True)
    
    name = Column(String, nullable=False)
    personalized_description = Column(String)
    status = Column(String, default="not_started")  # not_started, in_progress, completed, failed
    completion_progress = Column(Integer, default=0)  # For accumulation quests
    completion_target = Column(Integer, default=100)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    deadline = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="user_mq")
    template = relationship("MissionQuestTemplate", back_populates="user_mq")
    parent_mq = relationship("UserMissionQuest", remote_side=[id], backref="child_mq")
```

```python
# File: app/core/quest_matcher.py
from sqlalchemy.orm import Session
from app.models.mission_quest import UserMissionQuest
from typing import List, Dict

class QuestMatcher:
    """Match journal entries to active quests"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def check_quest_completion(
        self,
        user_id: str,
        ai_categories: Dict
    ) -> List[str]:
        """
        Check if journal entry completes any active quests
        
        Returns: List of completed quest IDs
        """
        active_quests = self.db.query(UserMissionQuest).filter(
            UserMissionQuest.user_id == user_id,
            UserMissionQuest.status.in_(["not_started", "in_progress"])
        ).all()
        
        completed_quest_ids = []
        
        for quest in active_quests:
            if self._matches_quest(quest, ai_categories):
                quest.status = "completed"
                quest.completed_at = datetime.utcnow()
                completed_quest_ids.append(quest.id)
        
        self.db.commit()
        return completed_quest_ids
    
    def _matches_quest(self, quest: UserMissionQuest, ai_categories: Dict) -> bool:
        """Determine if AI categories indicate quest completion"""
        # Simple keyword matching for MVP
        # TODO: More sophisticated matching with embeddings
        
        quest_keywords = quest.name.lower().split()
        entry_text = " ".join([
            theme.lower() for theme in ai_categories.get("themes", [])
        ] + [
            skill.lower() for skill in ai_categories.get("skills", [])
        ])
        
        # If 50%+ of quest keywords appear, consider it a match
        matches = sum(1 for kw in quest_keywords if kw in entry_text)
        return matches >= len(quest_keywords) * 0.5
```

**Checkpoint:** Create a quest, write a journal entry, verify quest completion is detected

---

### Day 18-19: Quest Generation (AI)
**Tasks:**
1. ✅ Build AI quest generator
2. ✅ Implement quest personalization
3. ✅ Seed GlobalMQBank with 10-15 starter quests

**Deliverables:**

```python
# File: app/ai/quest_generator.py
from app.ai.ollama_client import OllamaClient
from app.ai.prompts import QUEST_GENERATION_PROMPT
from typing import Dict

class QuestGenerator:
    """AI-powered quest generation"""
    
    def __init__(self):
        self.client = OllamaClient(model="llama3.2")
    
    def generate_quest(
        self,
        theme_name: str,
        user_context: Dict,
        quest_type: str = "daily"
    ) -> Dict:
        """
        Generate a personalized quest
        
        Returns:
        {
            "name": "Quest name",
            "description": "Personalized description",
            "type": "daily",
            "completion_condition": {"type": "yes_no"},
            "reward_xp": 50,
            "reward_coins": 10,
            "difficulty": "medium"
        }
        """
        prompt = QUEST_GENERATION_PROMPT.format(
            theme_name=theme_name,
            quest_type=quest_type,
            user_titles=user_context.get("titles", []),
            user_level=user_context.get("theme_level", 1),
            recent_skills=user_context.get("recent_skills", [])
        )
        
        try:
            result = self.client.generate_json(prompt)
            return result
        except Exception as e:
            print(f"Quest generation failed: {e}")
            # Fallback: generic quest
            return {
                "name": f"Practice {theme_name}",
                "description": f"Engage in {theme_name}-related activities today",
                "type": "daily",
                "completion_condition": {"type": "yes_no"},
                "reward_xp": 25,
                "reward_coins": 5,
                "difficulty": "medium"
            }
```

**Checkpoint:** Generate a quest via AI, verify it's contextually relevant

---

## WEEK 5: FRONTEND DASHBOARD

### **Goal:** Build a web dashboard to view character sheet and quests

### Day 20-23: Dashboard UI
**Tasks:**
1. ✅ Create HTML/CSS templates for dashboard
2. ✅ Implement character sheet view (Themes, Skills, Titles)
3. ✅ Implement quest list view
4. ✅ Add journal entry form

**Deliverables:**

```html
<!-- File: app/templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Status Window - {{ username }}</title>
    <style>
        /* Neurodivergent-friendly design */
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        }
        .status-window {
            border: 2px solid #ffd700;
            border-radius: 10px;
            padding: 20px;
            background: rgba(0, 0, 0, 0.5);
        }
        .xp-bar {
            width: 100%;
            height: 25px;
            background: #333;
            border-radius: 12px;
            overflow: hidden;
            position: relative;
        }
        .xp-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #4CAF50, #8BC34A);
            transition: width 0.5s ease;
        }
        .quest-item {
            background: rgba(255, 255, 255, 0.1);
            padding: 15px;
            margin: 10px 0;
            border-radius: 8px;
            border-left: 4px solid #ffd700;
        }
        .title-badge {
            display: inline-block;
            background: #ffd700;
            color: #000;
            padding: 5px 15px;
            border-radius: 20px;
            margin: 5px;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>
```

```html
<!-- File: app/templates/dashboard.html -->
{% extends "base.html" %}

{% block content %}
<div class="status-window">
    <h1>🎮 Status Window - {{ user.username }}</h1>
    
    <!-- Status Bars -->
    <div class="status-bars">
        <h3>Status</h3>
        <div>HP: <div class="xp-bar"><div class="xp-bar-fill" style="width: {{ stats.hp }}%"></div></div></div>
        <div>MP: <div class="xp-bar"><div class="xp-bar-fill" style="width: {{ stats.mp }}%"></div></div></div>
    </div>
    
    <!-- Themes -->
    <div class="themes">
        <h3>📚 Active Themes</h3>
        {% for theme in themes %}
        <div>
            <strong>{{ theme.name }}</strong> (Lv {{ theme.level }})
            <div class="xp-bar">
                <div class="xp-bar-fill" style="width: {{ (theme.xp / theme.xp_to_next_level) * 100 }}%"></div>
            </div>
        </div>
        {% endfor %}
    </div>
    
    <!-- Active Quests -->
    <div class="quests">
        <h3>🎯 Active Quests</h3>
        {% for quest in active_quests %}
        <div class="quest-item">
            <input type="checkbox" {% if quest.status == 'completed' %}checked{% endif %}>
            <strong>{{ quest.name }}</strong>
            <p>{{ quest.personalized_description }}</p>
        </div>
        {% endfor %}
    </div>
    
    <!-- Titles -->
    <div class="titles">
        <h3>⭐ Equipped Titles</h3>
        {% for title in equipped_titles %}
        <span class="title-badge">{{ title.title_template.name }}</span>
        {% endfor %}
    </div>
</div>

<a href="/journal">📝 New Journal Entry</a>
{% endblock %}
```

```python
# File: app/api/v1/character.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.utils.database import get_db
from app.models.user import User

router = APIRouter(prefix="/character", tags=["character"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/{username}", response_class=HTMLResponse)
async def get_character_sheet(
    username: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Render character sheet dashboard"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    active_quests = [mq for mq in user.user_mq if mq.status != "completed"]
    equipped_titles = [ut for ut in user.user_titles if ut.is_equipped]
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "themes": user.themes,
        "active_quests": active_quests,
        "equipped_titles": equipped_titles,
        "stats": user.stats or {"hp": 80, "mp": 60}
    })
```

**Checkpoint:** Visit `/character/{your_username}` and see your character sheet

---

## WEEK 6: POLISH & TESTING

### **Goal:** Bug fixes, testing, voice input (stretch), documentation

### Day 24-26: Testing & Bug Fixes
**Tasks:**
1. ✅ Write unit tests for core logic (XP calc, title awarding, quest matching)
2. ✅ End-to-end testing of full flow (journal → AI → XP → title)
3. ✅ Fix bugs discovered during testing

**Deliverables:**

```python
# File: tests/test_xp_calculator.py
import pytest
from app.core.xp_calculator import XPCalculator
from app.models.theme import Theme
from app.models.skill import Skill

def test_distribute_journal_xp(db_session):
    """Test XP distribution from journal entry"""
    # Setup
    user = create_test_user(db_session)
    theme = create_test_theme(db_session, user.id, "Education")
    skill = create_test_skill(db_session, user.id, "Python")
    
    xp_calc = XPCalculator(db_session)
    
    # Act
    xp_calc.distribute_journal_xp(
        user_id=user.id,
        theme_ids=[theme.id],
        skill_practice={skill.id: 30}
    )
    
    # Assert
    db_session.refresh(theme)
    db_session.refresh(skill)
    assert theme.xp == 10.0
    assert skill.practice_time_minutes == 30
    assert skill.xp == 15.0  # 30 minutes * 0.5 XP/min
```

**Checkpoint:** All tests pass, no critical bugs

---

### Day 27-28: Voice Input (Stretch Goal)
**Tasks:**
1. ✅ Integrate Faster-Whisper
2. ✅ Add voice file upload endpoint
3. ✅ Transcribe → Process same as text entry

**Deliverables:**

```python
# File: app/ai/whisper_client.py
from faster_whisper import WhisperModel

class WhisperClient:
    """Local speech-to-text using Faster-Whisper"""
    
    def __init__(self, model_size: str = "base"):
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
    
    def transcribe(self, audio_file_path: str) -> str:
        """Transcribe audio file to text"""
        segments, info = self.model.transcribe(audio_file_path, beam_size=5)
        text = " ".join([segment.text for segment in segments])
        return text
```

```python
# File: app/api/v1/journal.py (add endpoint)
from fastapi import UploadFile, File
from app.ai.whisper_client import WhisperClient
import shutil

@router.post("/voice_entry")
async def create_voice_journal_entry(
    user_id: str,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload voice recording → Transcribe → Process as journal entry"""
    # Save uploaded file
    file_path = f"data/voice_uploads/{audio.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)
    
    # Transcribe
    whisper = WhisperClient(model_size="base")
    transcribed_text = whisper.transcribe(file_path)
    
    # Process same as text entry
    entry = JournalEntryCreate(user_id=user_id, content=transcribed_text)
    return await create_journal_entry(entry, db)
```

**Checkpoint:** Upload voice recording, verify it's transcribed and processed correctly

---

### Day 29-30: Documentation & Deployment Prep
**Tasks:**
1. ✅ Write API documentation (Swagger auto-generated + custom notes)
2. ✅ Create user guide (how to use the system)
3. ✅ Set up automated backups
4. ✅ Prepare for friend beta deployment

**Deliverables:**
- API.md (comprehensive endpoint docs)
- USER_GUIDE.md (how to journal, view quests, etc.)
- Backup script running daily
- Docker compose file (optional) for easy deployment

**Checkpoint:** MVP is feature-complete and ready for personal use

---

## 🎯 MVP COMPLETION CHECKLIST

### Core Functionality
- [ ] Journal entry (text input)
- [ ] AI categorization (themes, skills, sentiment)
- [ ] XP distribution to themes/skills
- [ ] Theme/Skill leveling
- [ ] Title awarding (10+ titles in bank)
- [ ] Mission/Quest system (create, track, complete)
- [ ] Web dashboard (view character sheet, quests)
- [ ] Database persistence (SQLite)
- [ ] Error handling and logging

### Stretch Goals
- [ ] Voice input (Faster-Whisper)
- [ ] AI quest generation
- [ ] Corrosion system (basic)
- [ ] Coins/Currency
- [ ] Status bars (HP, Mental Health)

### Testing & Quality
- [ ] Unit tests for core logic
- [ ] End-to-end test of full flow
- [ ] No critical bugs
- [ ] Daily backup script

### Documentation
- [ ] API documentation
- [ ] User guide
- [ ] Code comments

---

## 🚀 POST-MVP ROADMAP (Future Phases)

### Phase 2: Enhanced UI & Social (Weeks 7-10)
- React/Vue.js PWA frontend
- Mobile-responsive design
- Friend sharing (Titles, Quests)
- Leaderboards

### Phase 3: Advanced Features (Weeks 11-14)
- Items/Inventory system
- Story Arcs (multi-stage missions)
- Advanced Skill Trees (branching, prerequisites)
- Data visualization (graphs, trends)

### Phase 4: Cloud Deployment (Weeks 15-18)
- PostgreSQL migration
- Cloud hosting (Railway/Render)
- Multi-user authentication
- Real-time syncing

---

**END OF DEVELOPMENT GUIDE**

_Follow this roadmap step-by-step, checking off tasks as you complete them. When stuck, consult PROJECT_SPECIFICATION.md for context, or ask Claude Code for implementation help._
