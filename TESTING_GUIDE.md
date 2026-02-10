# TESTING GUIDE: Comprehensive Test Strategy
## Test-Driven Development for "Life Sucks But You Got a Status Window Now"

**Philosophy:** Test everything that could break. Tests are documentation that runs.

**Goal:** Catch bugs before they reach production. Enable fearless refactoring.

---

## 📋 TABLE OF CONTENTS

1. [Testing Setup](#testing-setup)
2. [Test Structure & Conventions](#test-structure--conventions)
3. [Database Model Testing](#database-model-testing)
4. [API Endpoint Testing](#api-endpoint-testing)
5. [AI Integration Testing](#ai-integration-testing)
6. [Core Logic Testing](#core-logic-testing)
7. [Edge Cases & Failure Modes](#edge-cases--failure-modes)
8. [Test Data & Fixtures](#test-data--fixtures)
9. [Running Tests](#running-tests)
10. [CI/CD Integration](#cicd-integration)

---

## 🛠️ TESTING SETUP

### Install Testing Dependencies

```bash
pip install pytest pytest-cov pytest-mock faker freezegun
pip freeze > requirements.txt
```

**Packages:**
- `pytest`: Testing framework
- `pytest-cov`: Code coverage reports
- `pytest-mock`: Mocking support
- `faker`: Generate realistic test data
- `freezegun`: Freeze time for time-dependent tests

---

### Create pytest Configuration

**File:** `pytest.ini`

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    --verbose
    --cov=app
    --cov-report=html
    --cov-report=term-missing
    --strict-markers
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (database, API)
    slow: Slow tests (AI calls, etc.)
    ai: Tests that require Ollama running
```

---

### Create conftest.py (Global Fixtures)

**File:** `tests/conftest.py`

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.utils.database import Base
from app.models.user import User
from app.models.theme import Theme
from app.models.skill import Skill
from app.models.title import TitleTemplate, UserTitle
from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest
from app.models.journal_entry import JournalEntry
from faker import Faker

# Use in-memory SQLite for tests (fast!)
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def db_engine():
    """Create a fresh database engine for each test"""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a database session for each test"""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()

@pytest.fixture
def fake():
    """Faker instance for generating test data"""
    return Faker()

@pytest.fixture
def sample_user(db_session, fake):
    """Create a sample user for testing"""
    user = User(
        username=fake.user_name(),
        email=fake.email()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture
def sample_theme(db_session, sample_user):
    """Create a sample theme for testing"""
    theme = Theme(
        user_id=sample_user.id,
        name="Education",
        description="Learning and growing"
    )
    db_session.add(theme)
    db_session.commit()
    db_session.refresh(theme)
    return theme

@pytest.fixture
def sample_skill(db_session, sample_user, sample_theme):
    """Create a sample skill for testing"""
    skill = Skill(
        user_id=sample_user.id,
        theme_id=sample_theme.id,
        name="Python Programming",
        description="Learn Python"
    )
    db_session.add(skill)
    db_session.commit()
    db_session.refresh(skill)
    return skill
```

---

## 📐 TEST STRUCTURE & CONVENTIONS

### AAA Pattern (Arrange, Act, Assert)

```python
def test_user_creation(db_session):
    # ARRANGE: Set up test data
    username = "testuser"
    email = "test@example.com"
    
    # ACT: Perform the action
    user = User(username=username, email=email)
    db_session.add(user)
    db_session.commit()
    
    # ASSERT: Check the result
    assert user.id is not None
    assert user.username == username
    assert user.email == email
    assert user.created_at is not None
```

### Test Naming Convention

```python
# Pattern: test_<function/class>_<scenario>_<expected_outcome>

def test_theme_add_xp_below_threshold_no_level_up():
    """Adding XP below threshold should not trigger level-up"""
    pass

def test_theme_add_xp_above_threshold_triggers_level_up():
    """Adding XP above threshold should trigger level-up"""
    pass

def test_skill_practice_time_zero_minutes_raises_value_error():
    """Adding zero practice time should raise ValueError"""
    pass
```

### Test Organization

```
tests/
├── conftest.py                  # Global fixtures
├── test_models/                 # Database model tests
│   ├── test_user.py
│   ├── test_theme.py
│   ├── test_skill.py
│   ├── test_title.py
│   ├── test_mission_quest.py
│   └── test_journal_entry.py
├── test_api/                    # API endpoint tests
│   ├── test_journal_endpoints.py
│   ├── test_character_endpoints.py
│   └── test_quest_endpoints.py
├── test_ai/                     # AI integration tests
│   ├── test_categorizer.py
│   ├── test_quest_generator.py
│   └── test_whisper.py
└── test_core/                   # Core logic tests
    ├── test_xp_calculator.py
    ├── test_title_awarder.py
    └── test_quest_matcher.py
```

---

## 🗄️ DATABASE MODEL TESTING

### What to Test for EVERY Model

**File:** `tests/test_models/test_user.py`

```python
import pytest
from app.models.user import User
from sqlalchemy.exc import IntegrityError

class TestUserModel:
    """Comprehensive tests for User model"""
    
    # ===== CREATION TESTS =====
    
    def test_user_creation_with_valid_data(self, db_session, fake):
        """Should create user with all required fields"""
        # Arrange
        username = fake.user_name()
        email = fake.email()
        
        # Act
        user = User(username=username, email=email)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        
        # Assert
        assert user.id is not None
        assert user.username == username
        assert user.email == email
        assert user.created_at is not None
        assert user.is_active is True  # Default value
    
    def test_user_creation_generates_uuid(self, db_session, fake):
        """Should auto-generate UUID for primary key"""
        # Act
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()
        
        # Assert
        assert user.id is not None
        assert len(user.id) == 36  # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert user.id.count('-') == 4
    
    # ===== CONSTRAINT TESTS =====
    
    def test_user_creation_duplicate_username_raises_error(self, db_session, fake):
        """Should raise IntegrityError for duplicate username"""
        # Arrange
        username = fake.user_name()
        user1 = User(username=username, email=fake.email())
        db_session.add(user1)
        db_session.commit()
        
        # Act & Assert
        with pytest.raises(IntegrityError):
            user2 = User(username=username, email=fake.email())
            db_session.add(user2)
            db_session.commit()
    
    def test_user_creation_duplicate_email_raises_error(self, db_session, fake):
        """Should raise IntegrityError for duplicate email"""
        # Arrange
        email = fake.email()
        user1 = User(username=fake.user_name(), email=email)
        db_session.add(user1)
        db_session.commit()
        
        # Act & Assert
        with pytest.raises(IntegrityError):
            user2 = User(username=fake.user_name(), email=email)
            db_session.add(user2)
            db_session.commit()
    
    # ===== RELATIONSHIP TESTS =====
    
    def test_user_themes_relationship_is_bidirectional(self, db_session, sample_user):
        """Should have bidirectional relationship with themes"""
        # Arrange & Act
        from app.models.theme import Theme
        theme = Theme(user_id=sample_user.id, name="Test Theme")
        db_session.add(theme)
        db_session.commit()
        db_session.refresh(sample_user)
        
        # Assert
        assert len(sample_user.themes) == 1
        assert sample_user.themes[0].name == "Test Theme"
        assert theme.user.username == sample_user.username
    
    def test_user_deletion_cascades_to_themes(self, db_session, sample_user):
        """Deleting user should cascade delete all themes"""
        # Arrange
        from app.models.theme import Theme
        theme1 = Theme(user_id=sample_user.id, name="Theme 1")
        theme2 = Theme(user_id=sample_user.id, name="Theme 2")
        db_session.add_all([theme1, theme2])
        db_session.commit()
        
        # Act
        db_session.delete(sample_user)
        db_session.commit()
        
        # Assert
        remaining_themes = db_session.query(Theme).filter(Theme.user_id == sample_user.id).all()
        assert len(remaining_themes) == 0
    
    # ===== EDGE CASES =====
    
    def test_user_creation_with_empty_username_raises_error(self, db_session, fake):
        """Should raise error for empty username"""
        with pytest.raises(Exception):  # SQLAlchemy will raise some error
            user = User(username="", email=fake.email())
            db_session.add(user)
            db_session.commit()
    
    def test_user_creation_with_none_email_raises_error(self, db_session, fake):
        """Should raise error for None email"""
        with pytest.raises(Exception):
            user = User(username=fake.user_name(), email=None)
            db_session.add(user)
            db_session.commit()
```

---

### Theme Model Testing Template

**File:** `tests/test_models/test_theme.py`

```python
import pytest
from app.models.theme import Theme

class TestThemeModel:
    """Comprehensive tests for Theme model"""
    
    # ===== XP & LEVELING TESTS =====
    
    def test_theme_add_xp_below_threshold_no_level_up(self, db_session, sample_user):
        """Adding XP below threshold should not trigger level-up"""
        # Arrange
        theme = Theme(user_id=sample_user.id, name="Test", xp=0, level=0, xp_to_next_level=100)
        db_session.add(theme)
        db_session.commit()
        
        # Act
        theme.add_xp(50)
        db_session.commit()
        
        # Assert
        assert theme.xp == 50
        assert theme.level == 0
    
    def test_theme_add_xp_at_threshold_triggers_level_up(self, db_session, sample_user):
        """Adding XP to reach threshold should trigger level-up"""
        # Arrange
        theme = Theme(user_id=sample_user.id, name="Test", xp=0, level=0, xp_to_next_level=100)
        db_session.add(theme)
        db_session.commit()
        
        # Act
        theme.add_xp(100)
        db_session.commit()
        
        # Assert
        assert theme.level == 1
        assert theme.xp == 0  # Overflow should reset
        assert theme.xp_to_next_level > 100  # Next level requires more XP
    
    def test_theme_add_xp_above_threshold_carries_overflow(self, db_session, sample_user):
        """Adding XP above threshold should carry overflow to next level"""
        # Arrange
        theme = Theme(user_id=sample_user.id, name="Test", xp=0, level=0, xp_to_next_level=100)
        db_session.add(theme)
        db_session.commit()
        
        # Act
        theme.add_xp(150)
        db_session.commit()
        
        # Assert
        assert theme.level == 1
        assert theme.xp == 50  # 150 - 100 = 50 overflow
    
    def test_theme_add_xp_multiple_level_ups(self, db_session, sample_user):
        """Adding large XP should trigger multiple level-ups"""
        # Arrange
        theme = Theme(user_id=sample_user.id, name="Test", xp=0, level=0, xp_to_next_level=100)
        db_session.add(theme)
        db_session.commit()
        
        # Act
        theme.add_xp(500)  # Should level up multiple times
        db_session.commit()
        
        # Assert
        assert theme.level >= 2  # At least 2 levels
    
    def test_theme_xp_calculation_exponential_scaling(self, db_session, sample_user):
        """XP requirements should scale exponentially"""
        # Arrange
        theme = Theme(user_id=sample_user.id, name="Test", level=0)
        db_session.add(theme)
        db_session.commit()
        
        # Act
        xp_level_0 = theme.calculate_next_level_xp()
        theme.level = 5
        xp_level_5 = theme.calculate_next_level_xp()
        
        # Assert
        assert xp_level_5 > xp_level_0  # Higher level = more XP needed
        assert xp_level_5 >= xp_level_0 * 1.5  # Should be significantly more
    
    # ===== HIERARCHY TESTS (Self-Referential) =====
    
    def test_theme_parent_child_relationship(self, db_session, sample_user):
        """Should support parent-child theme hierarchy"""
        # Arrange
        parent_theme = Theme(user_id=sample_user.id, name="Education")
        db_session.add(parent_theme)
        db_session.commit()
        
        # Act
        child_theme = Theme(user_id=sample_user.id, name="Programming", parent_theme_id=parent_theme.id)
        db_session.add(child_theme)
        db_session.commit()
        db_session.refresh(parent_theme)
        
        # Assert
        assert child_theme.parent_theme.name == "Education"
        assert len(parent_theme.sub_themes) == 1
        assert parent_theme.sub_themes[0].name == "Programming"
    
    def test_theme_multi_level_hierarchy(self, db_session, sample_user):
        """Should support multi-level theme hierarchy"""
        # Arrange
        level1 = Theme(user_id=sample_user.id, name="Education")
        db_session.add(level1)
        db_session.commit()
        
        level2 = Theme(user_id=sample_user.id, name="Programming", parent_theme_id=level1.id)
        db_session.add(level2)
        db_session.commit()
        
        # Act
        level3 = Theme(user_id=sample_user.id, name="Python", parent_theme_id=level2.id)
        db_session.add(level3)
        db_session.commit()
        
        # Assert
        assert level3.parent_theme.name == "Programming"
        assert level3.parent_theme.parent_theme.name == "Education"
    
    # ===== CORROSION TESTS =====
    
    def test_theme_default_corrosion_level_is_fresh(self, db_session, sample_user):
        """New themes should have 'Fresh' corrosion level"""
        # Act
        theme = Theme(user_id=sample_user.id, name="Test")
        db_session.add(theme)
        db_session.commit()
        
        # Assert
        assert theme.corrosion_level == "Fresh"
    
    # ===== EDGE CASES =====
    
    def test_theme_negative_xp_raises_error_or_handles_gracefully(self, db_session, sample_user):
        """Adding negative XP should be handled appropriately"""
        # Arrange
        theme = Theme(user_id=sample_user.id, name="Test", xp=50)
        db_session.add(theme)
        db_session.commit()
        
        # Act & Assert (choose one behavior)
        # Option A: Raise error
        with pytest.raises(ValueError):
            theme.add_xp(-100)
        
        # Option B: Clamp to zero (implement this in model if chosen)
        # theme.add_xp(-100)
        # assert theme.xp == 0
```

---

### Skill Model Testing Template

**File:** `tests/test_models/test_skill.py`

```python
import pytest
from app.models.skill import Skill

class TestSkillModel:
    """Comprehensive tests for Skill model"""
    
    # ===== RANK PROGRESSION TESTS =====
    
    def test_skill_rank_progression_beginner_to_amateur(self, db_session, sample_user):
        """Should progress from Beginner to Amateur at level 5"""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill", level=0, rank="Beginner")
        db_session.add(skill)
        db_session.commit()
        
        # Act
        skill.level = 5
        skill.update_rank()
        
        # Assert
        assert skill.rank == "Amateur"
    
    def test_skill_rank_all_transitions(self, db_session, sample_user):
        """Should correctly transition through all ranks"""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test Skill")
        db_session.add(skill)
        db_session.commit()
        
        # Act & Assert
        skill.level = 0
        skill.update_rank()
        assert skill.rank == "Beginner"
        
        skill.level = 5
        skill.update_rank()
        assert skill.rank == "Amateur"
        
        skill.level = 15
        skill.update_rank()
        assert skill.rank == "Intermediate"
        
        skill.level = 30
        skill.update_rank()
        assert skill.rank == "Advanced"
        
        skill.level = 50
        skill.update_rank()
        assert skill.rank == "Expert"
        
        skill.level = 80
        skill.update_rank()
        assert skill.rank == "Master"
    
    # ===== PRACTICE TIME TESTS =====
    
    def test_skill_add_practice_time_increments_total(self, db_session, sample_user):
        """Adding practice time should increment total"""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test", practice_time_minutes=0)
        db_session.add(skill)
        db_session.commit()
        
        # Act
        skill.add_practice_time(30)
        db_session.commit()
        
        # Assert
        assert skill.practice_time_minutes == 30
    
    def test_skill_add_practice_time_awards_xp(self, db_session, sample_user):
        """Adding practice time should award XP"""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test", xp=0)
        db_session.add(skill)
        db_session.commit()
        
        # Act
        skill.add_practice_time(30, xp_multiplier=1.0)  # 30 min * 0.5 = 15 XP
        db_session.commit()
        
        # Assert
        assert skill.xp == 15.0
    
    def test_skill_add_practice_time_with_multiplier(self, db_session, sample_user):
        """XP multiplier should affect XP gained from practice"""
        # Arrange
        skill = Skill(user_id=sample_user.id, name="Test", xp=0)
        db_session.add(skill)
        db_session.commit()
        
        # Act
        skill.add_practice_time(30, xp_multiplier=2.0)  # 30 min * 0.5 * 2.0 = 30 XP
        db_session.commit()
        
        # Assert
        assert skill.xp == 30.0
    
    # ===== SKILL TREE TESTS =====
    
    def test_skill_tree_parent_child_relationship(self, db_session, sample_user):
        """Should support parent-child skill trees"""
        # Arrange
        parent_skill = Skill(user_id=sample_user.id, name="Programming")
        db_session.add(parent_skill)
        db_session.commit()
        
        # Act
        child_skill = Skill(user_id=sample_user.id, name="Python", parent_skill_id=parent_skill.id)
        db_session.add(child_skill)
        db_session.commit()
        db_session.refresh(parent_skill)
        
        # Assert
        assert child_skill.parent_skill.name == "Programming"
        assert len(parent_skill.child_skills) == 1
        assert parent_skill.child_skills[0].name == "Python"
    
    def test_skill_tree_multiple_children(self, db_session, sample_user):
        """Should support multiple child skills (parallel branches)"""
        # Arrange
        parent = Skill(user_id=sample_user.id, name="Programming")
        db_session.add(parent)
        db_session.commit()
        
        # Act
        child1 = Skill(user_id=sample_user.id, name="Python", parent_skill_id=parent.id)
        child2 = Skill(user_id=sample_user.id, name="JavaScript", parent_skill_id=parent.id)
        db_session.add_all([child1, child2])
        db_session.commit()
        db_session.refresh(parent)
        
        # Assert
        assert len(parent.child_skills) == 2
        child_names = [s.name for s in parent.child_skills]
        assert "Python" in child_names
        assert "JavaScript" in child_names
```

---

### Quest Matcher & Autostart (Core Logic)

**File:** `tests/test_core/test_quest_matcher.py`

```python
def test_autostart_requires_condition(db_session, sample_user, quest_factory):
    """Not-started quests should not autostart without a condition"""
    quest = quest_factory(user_id=sample_user.id, status="not_started", autostart=True)
    assert quest.autostart_condition is None
    # matcher should skip this quest entirely

def test_autostart_uses_template_condition(db_session, sample_user, template_factory, quest_factory):
    """Instance should inherit template autostart_condition when unset"""
    template = template_factory(autostart=True, autostart_condition={"type": "keyword_match", "keywords": ["run"]})
    quest = quest_factory(user_id=sample_user.id, template_id=template.id, autostart=True, autostart_condition=None)
    # matcher should use template condition and start on keyword match
```

**Related core tests:**
- Title XP multipliers should ignore expired titles (e.g., `tests/test_core/test_xp_calculator.py`)
- Skill rank thresholds should use `>=` boundary checks (e.g., `tests/test_models/test_skill.py`)

## 🌐 API ENDPOINT TESTING

**File:** `tests/test_api/test_journal_endpoints.py`

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestJournalEndpoints:
    """Test journal API endpoints"""
    
    def test_create_journal_entry_success(self, sample_user):
        """Should create journal entry with valid data"""
        # Arrange
        payload = {
            "user_id": sample_user.id,
            "content": "Coded for 2 hours today, feeling productive!"
        }
        
        # Act
        response = client.post("/journal/entry", json=payload)
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == payload["content"]
        assert "id" in data
    
    def test_create_journal_entry_invalid_user_id(self):
        """Should return 404 for non-existent user"""
        # Arrange
        payload = {
            "user_id": "non-existent-uuid",
            "content": "Test"
        }
        
        # Act
        response = client.post("/journal/entry", json=payload)
        
        # Assert
        assert response.status_code == 404
    
    def test_create_journal_entry_empty_content(self, sample_user):
        """Should reject empty content"""
        # Arrange
        payload = {
            "user_id": sample_user.id,
            "content": ""
        }
        
        # Act
        response = client.post("/journal/entry", json=payload)
        
        # Assert
        assert response.status_code == 422  # Validation error
```

---

## 🤖 AI INTEGRATION TESTING

**File:** `tests/test_ai/test_categorizer.py`

```python
import pytest
from app.ai.categorizer import JournalCategorizer

@pytest.mark.ai  # Mark tests that require Ollama
class TestJournalCategorizer:
    """Test AI categorization"""
    
    def test_categorizer_identifies_theme(self):
        """Should identify theme from journal entry"""
        # Arrange
        categorizer = JournalCategorizer()
        entry = "Went to the gym and did 50 pushups"
        user_themes = [{"id": "theme-1", "name": "Physical Health"}]
        
        # Act
        result = categorizer.categorize_entry(entry, user_themes, [], [])
        
        # Assert
        assert "themes" in result
        assert len(result["themes"]) > 0
    
    @pytest.mark.slow
    def test_categorizer_performance(self):
        """Categorization should complete in <5 seconds"""
        # Test that AI doesn't timeout
        pass
```

---

## ⚡ EDGE CASES & FAILURE MODES

### Always Test These Scenarios

```python
# ===== NULL/EMPTY VALUES =====
def test_handles_null_input():
    """Should handle None/null gracefully"""
    pass

def test_handles_empty_string():
    """Should handle empty string gracefully"""
    pass

def test_handles_empty_list():
    """Should handle empty list gracefully"""
    pass

# ===== BOUNDARY CONDITIONS =====
def test_zero_value():
    """Should handle zero correctly"""
    pass

def test_negative_value():
    """Should reject or clamp negative values"""
    pass

def test_maximum_value():
    """Should handle max int/float"""
    pass

# ===== DATA TYPE MISMATCHES =====
def test_string_instead_of_int():
    """Should raise TypeError for wrong type"""
    pass

def test_int_instead_of_string():
    """Should handle type coercion or raise error"""
    pass

# ===== CONCURRENT ACCESS =====
def test_concurrent_updates():
    """Should handle race conditions"""
    pass

# ===== CASCADING DELETES =====
def test_delete_cascades_correctly():
    """Deleting parent should delete children"""
    pass

def test_orphan_prevention():
    """Should prevent orphaned records"""
    pass
```

---

## 🎯 RUNNING TESTS

### Run All Tests
```bash
pytest
```

### Run Specific Test File
```bash
pytest tests/test_models/test_user.py
```

### Run Specific Test Class
```bash
pytest tests/test_models/test_user.py::TestUserModel
```

### Run Specific Test Function
```bash
pytest tests/test_models/test_user.py::TestUserModel::test_user_creation_with_valid_data
```

### Run Tests by Marker
```bash
pytest -m unit          # Only unit tests
pytest -m integration   # Only integration tests
pytest -m "not slow"    # Exclude slow tests
```

### Run with Coverage
```bash
pytest --cov=app --cov-report=html
# Open htmlcov/index.html to see coverage report
```

### Run in Watch Mode (Auto-rerun on file changes)
```bash
pip install pytest-watch
ptw
```

---

## 📊 TEST COVERAGE REQUIREMENTS

**Targets:**
- **Models:** 90%+ coverage (critical business logic)
- **API Endpoints:** 80%+ coverage
- **Core Logic:** 95%+ coverage (XP calc, title awarding, etc.)
- **AI Integration:** 70%+ coverage (hard to mock, focus on happy path)

**Check Coverage:**
```bash
pytest --cov=app --cov-report=term-missing
```

---

## 🔄 CI/CD INTEGRATION

**File:** `.github/workflows/tests.yml`

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests
        run: |
          pytest --cov=app --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## 🎓 TESTING BEST PRACTICES

1. **Test Behavior, Not Implementation**
   - ❌ Bad: `assert user._internal_method() == True`
   - ✅ Good: `assert user.is_active == True`

2. **One Assert Per Test (When Possible)**
   - Makes failures easier to debug
   - Exception: Related assertions (e.g., checking multiple fields after creation)

3. **Use Descriptive Test Names**
   - ❌ Bad: `test_user_1()`
   - ✅ Good: `test_user_creation_with_duplicate_email_raises_error()`

4. **Test Failure Cases, Not Just Success**
   - Every function should have at least 2 tests: success + failure

5. **Mock External Dependencies**
   - Don't call real Ollama API in tests (mock it)
   - Don't send real emails (mock SMTP)

6. **Keep Tests Independent**
   - Each test should run in isolation
   - Use fixtures, not global state

---

## 📝 TESTING CHECKLIST (For Each New Feature)

Before marking a feature "done", ensure:

- [ ] Unit tests for all new functions/methods
- [ ] Integration tests for API endpoints
- [ ] Edge case tests (null, empty, negative, etc.)
- [ ] Relationship tests (if database models involved)
- [ ] Error handling tests (try/except paths)
- [ ] Coverage >80% for new code
- [ ] All tests pass locally
- [ ] Tests added to CI/CD pipeline

---

**END OF TESTING GUIDE**

_Test early, test often, refactor fearlessly!_
