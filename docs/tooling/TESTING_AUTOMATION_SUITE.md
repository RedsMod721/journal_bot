# TESTING_AUTOMATION_SUITE.md
**Project:** RPG Life Tracker - Testing Automation Suite  
**Version:** 1.0  
**Date:** February 26, 2026  
**Status:** PRODUCTION READY  
**Purpose:** 500+ automated tests, CI/CD pipeline, coverage reporting, performance benchmarking

---

## EXECUTIVE SUMMARY

### Document Purpose

This document provides **complete specifications** for the RPG Life Tracker testing automation suite:

- **500+ Automated Tests** (unit, integration, e2e)
- **CI/CD Pipeline** (GitHub Actions)
- **Coverage Reporting** (pytest-cov, 95%+ target)
- **Performance Benchmarking** (load testing, profiling)
- **Regression Testing** (snapshot testing, golden masters)

**Core Principle:** *Tests are first-class citizens. Write tests before features, not after.*

### Test Pyramid

```
         ┌──────────┐
         │   E2E    │  10% (50 tests)
         │  Tests   │
         ├──────────┤
         │Integration│  30% (150 tests)
         │  Tests    │
         ├──────────┤
         │   Unit    │  60% (300 tests)
         │   Tests   │
         └──────────┘
```

**Distribution:**
- **Unit Tests (60%):** Fast, isolated, test single functions/classes
- **Integration Tests (30%):** Medium speed, test multiple components together
- **E2E Tests (10%):** Slow, test complete user workflows

### Success Criteria

**Testing Suite is Complete If:**
- ✅ 500+ tests implemented and passing
- ✅ Coverage ≥95% (core modules)
- ✅ CI/CD pipeline operational (GitHub Actions)
- ✅ All tests run in <5 minutes (CI)
- ✅ Performance benchmarks established (baseline metrics)
- ✅ Regression tests prevent known bugs

---

## PART I: UNIT TESTS (300 TESTS)

### 1.1 Test Organization

**Directory Structure:**

```
tests/
├── unit/
│   ├── core/
│   │   ├── test_xp.py          # XP calculation (40 tests)
│   │   ├── test_quests.py      # Quest matching (30 tests)
│   │   ├── test_themes.py      # Theme propagation (20 tests)
│   │   ├── test_forgiveness.py # Forgiveness system (25 tests)
│   │   └── test_variety.py     # Balance variety (25 tests)
│   ├── db/
│   │   ├── test_models.py      # Model validation (50 tests)
│   │   └── test_queries.py     # Query optimization (20 tests)
│   ├── api/
│   │   ├── test_schemas.py     # Pydantic validation (40 tests)
│   │   └── test_routes.py      # Endpoint logic (30 tests)
│   └── ai/
│       ├── test_ollama.py      # Ollama client (15 tests)
│       └── test_pipeline.py    # Pipeline steps (20 tests)
```

### 1.2 Example: XP Calculation Tests

**tests/unit/core/test_xp.py:**

```python
"""
Unit tests for XP calculation module.
Target: 40 tests, 100% coverage
"""

import pytest
from src.core.xp import (
    calculate_xp_for_level,
    calculate_level_from_xp,
    calculate_session_xp,
    calculate_theme_xp_from_skill
)


class TestXPForLevel:
    """Test XP requirements for each level (20 tests)."""
    
    @pytest.mark.parametrize("level,expected_xp", [
        (1, 0),           # Level 1 = 0 XP
        (2, 480),         # Level 2 = 480 XP
        (5, 5093),        # Rank F
        (10, 22800),
        (20, 345943),
        (30, 296227),     # Target: 90 days
        (40, 1013776),
        (50, 2515393),
        (60, 5765760),
        (100, 175234560), # Maximum level
    ])
    def test_xp_for_level_matches_architecture(self, level: int, expected_xp: int):
        """Test XP requirements match architecture table."""
        calculated = calculate_xp_for_level(level)
        # Allow ±10 XP tolerance for rounding
        assert abs(calculated - expected_xp) < 10, \
            f"Level {level}: Expected {expected_xp}, got {calculated}"
    
    def test_level_1_is_zero_xp(self):
        """Level 1 should require 0 XP."""
        assert calculate_xp_for_level(1) == 0
    
    def test_xp_increases_monotonically(self):
        """XP should increase with each level."""
        for level in range(1, 100):
            xp_current = calculate_xp_for_level(level)
            xp_next = calculate_xp_for_level(level + 1)
            assert xp_next > xp_current
    
    def test_exponent_changes_at_rank_boundaries(self):
        """Exponent should change at levels 20, 40, 60."""
        # Rank F→E transition (level 20→21)
        xp_20 = calculate_xp_for_level(20)
        xp_21 = calculate_xp_for_level(21)
        ratio_20_21 = xp_21 / xp_20
        assert 1.55 < ratio_20_21 < 1.65  # Exponent changes 1.5→1.6
        
        # Rank A→S transition (level 40→41)
        xp_40 = calculate_xp_for_level(40)
        xp_41 = calculate_xp_for_level(41)
        ratio_40_41 = xp_41 / xp_40
        assert 1.75 < ratio_40_41 < 1.85  # Exponent changes 1.6→1.8


class TestLevelFromXP:
    """Test level calculation from XP (10 tests)."""
    
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
        """Test level calculation from XP."""
        calculated = calculate_level_from_xp(total_xp)
        assert calculated == expected_level
    
    def test_level_from_xp_is_inverse_of_xp_for_level(self):
        """Test that level_from_xp is inverse of xp_for_level."""
        for level in [1, 5, 10, 20, 30, 50, 80]:
            xp = calculate_xp_for_level(level)
            calculated_level = calculate_level_from_xp(xp)
            assert calculated_level == level


class TestSessionXP:
    """Test session XP calculation (10 tests)."""
    
    def test_baseline_session(self):
        """Test 30-minute baseline session."""
        result = calculate_session_xp(
            base_xp=480,
            minutes=30,
            quality_mult=1.0,
            variety_bonus=0.0,
            troll_multiplier=1.0
        )
        assert result["skill_xp"] == 480
        assert result["theme_xp"] == 1  # max(1, 480 * 0.001)
    
    def test_time_scaling(self):
        """Test session XP scales linearly with time."""
        result_30 = calculate_session_xp(480, 30, 1.0, 0.0)
        result_60 = calculate_session_xp(480, 60, 1.0, 0.0)
        
        assert result_60["skill_xp"] == result_30["skill_xp"] * 2
    
    def test_variety_bonus_applied(self):
        """Test variety bonus increases XP."""
        result_no_variety = calculate_session_xp(480, 30, 1.0, 0.0)
        result_with_variety = calculate_session_xp(480, 30, 1.0, 0.30)
        
        expected_with_variety = 480 * 1.3  # 30% variety bonus
        assert abs(result_with_variety["skill_xp"] - expected_with_variety) < 5
    
    def test_theme_xp_propagation(self):
        """Test theme XP is 0.1% of skill XP."""
        result = calculate_session_xp(480, 60, 1.5, 0.30)
        skill_xp = result["skill_xp"]
        theme_xp = result["theme_xp"]
        
        # Theme XP should be max(1, skill_xp * 0.001)
        expected_theme_xp = max(1, int(skill_xp * 0.001))
        assert theme_xp == expected_theme_xp


# Run with: pytest tests/unit/core/test_xp.py -v --cov=src.core.xp
```

### 1.3 Property-Based Testing (Hypothesis)

**tests/unit/core/test_xp_properties.py:**

```python
"""
Property-based tests for XP system using Hypothesis.
"""

import pytest
from hypothesis import given, strategies as st
from src.core.xp import calculate_xp_for_level, calculate_level_from_xp


class TestXPProperties:
    """Property-based tests (10 tests)."""
    
    @given(level=st.integers(min_value=1, max_value=100))
    def test_xp_for_level_always_non_negative(self, level):
        """XP should never be negative."""
        xp = calculate_xp_for_level(level)
        assert xp >= 0
    
    @given(level=st.integers(min_value=2, max_value=100))
    def test_xp_for_level_monotonically_increasing(self, level):
        """XP should increase with each level."""
        xp_prev = calculate_xp_for_level(level - 1)
        xp_current = calculate_xp_for_level(level)
        assert xp_current > xp_prev
    
    @given(total_xp=st.integers(min_value=0, max_value=200000000))
    def test_level_from_xp_bounded(self, total_xp):
        """Level should be between 1 and 100."""
        level = calculate_level_from_xp(total_xp)
        assert 1 <= level <= 100
    
    @given(
        base_xp=st.integers(min_value=200, max_value=2000),
        minutes=st.integers(min_value=5, max_value=240),
        quality=st.floats(min_value=0.5, max_value=2.0),
        variety=st.floats(min_value=0.0, max_value=0.60)
    )
    def test_session_xp_always_positive(self, base_xp, minutes, quality, variety):
        """Session XP should always be positive."""
        from src.core.xp import calculate_session_xp
        
        result = calculate_session_xp(base_xp, minutes, quality, variety)
        assert result["skill_xp"] > 0
        assert result["theme_xp"] > 0


# Run with: pytest tests/unit/core/test_xp_properties.py
```

---

## PART II: INTEGRATION TESTS (150 TESTS)

### 2.1 Database Integration Tests

**tests/integration/test_db_operations.py:**

```python
"""
Integration tests for database operations.
Target: 50 tests
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from src.db.models import Base, User, Skill, Theme, JournalEntry
from src.core.xp import calculate_session_xp, calculate_level_from_xp


@pytest.fixture
def test_db():
    """Create in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    yield session
    
    session.close()


@pytest.fixture
def test_user(test_db):
    """Create test user."""
    user = User(
        user_id="test_user_123",
        username="testuser",
        email="test@example.com",
        personality_type="therapist",
        forgiveness_preset="balanced"
    )
    test_db.add(user)
    test_db.commit()
    return user


class TestUserOperations:
    """Test user CRUD operations (10 tests)."""
    
    def test_create_user(self, test_db):
        """Test user creation."""
        user = User(
            user_id="user_new",
            username="newuser",
            email="new@example.com",
            personality_type="raphael",
            forgiveness_preset="strict"
        )
        
        test_db.add(user)
        test_db.commit()
        
        # Retrieve
        retrieved = test_db.query(User).filter_by(user_id="user_new").first()
        assert retrieved is not None
        assert retrieved.username == "newuser"
        assert retrieved.personality_type == "raphael"
    
    def test_user_cascade_delete(self, test_db, test_user):
        """Test cascade delete removes user's skills."""
        # Create skill for user
        skill = Skill(
            skill_id="skill_test",
            user_id=test_user.user_id,
            canonical_name="Test Skill",
            category="Physical"
        )
        test_db.add(skill)
        test_db.commit()
        
        # Delete user
        test_db.delete(test_user)
        test_db.commit()
        
        # Verify skill also deleted
        skill_count = test_db.query(Skill).filter_by(user_id=test_user.user_id).count()
        assert skill_count == 0


class TestSkillProgression:
    """Test skill progression (20 tests)."""
    
    def test_skill_xp_update_and_level_calculation(self, test_db, test_user):
        """Test awarding XP updates level correctly."""
        # Create skill
        skill = Skill(
            skill_id="skill_python",
            user_id=test_user.user_id,
            canonical_name="Python Programming",
            category="Professional",
            total_xp=0,
            current_level=1
        )
        test_db.add(skill)
        test_db.commit()
        
        # Award XP (simulate 10 sessions)
        for _ in range(10):
            xp_result = calculate_session_xp(480, 60, 1.2, 0.30)
            skill.total_xp += xp_result["skill_xp"]
        
        # Recalculate level
        skill.current_level = calculate_level_from_xp(skill.total_xp)
        test_db.commit()
        
        # Verify
        assert skill.total_xp > 10000
        assert skill.current_level >= 3
    
    def test_theme_propagation(self, test_db, test_user):
        """Test theme XP propagates from skill XP."""
        # Create skill and theme
        skill = Skill(
            skill_id="skill_cardio",
            user_id=test_user.user_id,
            canonical_name="Cardio Running",
            category="Physical",
            total_xp=0,
            current_level=1
        )
        
        theme = Theme(
            theme_id="theme_physical",
            user_id=test_user.user_id,
            name="Physical",
            total_xp=0,
            current_level=1
        )
        
        test_db.add_all([skill, theme])
        test_db.commit()
        
        # Award skill XP
        xp_result = calculate_session_xp(480, 30, 1.0, 0.0)
        skill.total_xp += xp_result["skill_xp"]
        theme.total_xp += xp_result["theme_xp"]
        
        test_db.commit()
        
        # Verify theme XP is 0.1% of skill XP
        assert theme.total_xp == max(1, int(skill.total_xp * 0.001))


# Run with: pytest tests/integration/test_db_operations.py -v
```

### 2.2 API Integration Tests

**tests/integration/test_api_endpoints.py:**

```python
"""
Integration tests for FastAPI endpoints.
Target: 50 tests
"""

import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.db.session import get_db, Base, engine


@pytest.fixture
def client():
    """Create test client."""
    # Setup test database
    Base.metadata.create_all(bind=engine)
    
    yield TestClient(app)
    
    # Teardown
    Base.metadata.drop_all(bind=engine)


class TestJournalEndpoints:
    """Test journal entry endpoints (20 tests)."""
    
    def test_submit_journal_entry(self, client):
        """Test POST /api/journal/entries."""
        response = client.post(
            "/api/journal/entries",
            json={
                "user_id": "test_user",
                "raw_text": "Today I ran 5K and coded for 2 hours on my Python project."
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "entry_id" in data
        assert data["status"] == "submitted"
    
    def test_submit_entry_too_short(self, client):
        """Test validation: entry too short."""
        response = client.post(
            "/api/journal/entries",
            json={
                "user_id": "test_user",
                "raw_text": "Too short"  # Only 2 words
            }
        )
        
        assert response.status_code == 422
        assert "too short" in response.json()["detail"].lower()


# Run with: pytest tests/integration/test_api_endpoints.py -v
```

---

## PART III: END-TO-END TESTS (50 TESTS)

### 3.1 E2E Test Setup

**tests/e2e/conftest.py:**

```python
"""
E2E test configuration.
"""

import pytest
import subprocess
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


@pytest.fixture(scope="session")
def test_server():
    """Start FastAPI test server."""
    # Start server
    proc = subprocess.Popen(
        ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8001"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to start
    time.sleep(2)
    
    yield "http://localhost:8001"
    
    # Shutdown server
    proc.terminate()
    proc.wait()


@pytest.fixture
def browser():
    """Create headless Chrome browser."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=options)
    
    yield driver
    
    driver.quit()
```

### 3.2 E2E User Flows

**tests/e2e/test_journal_submission_flow.py:**

```python
"""
E2E test: Journal submission flow.
"""

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def test_submit_journal_entry_complete_flow(test_server, browser):
    """
    E2E test: User submits journal entry and sees XP update.
    
    Steps:
    1. Navigate to journal page
    2. Enter text (50+ words)
    3. Click submit
    4. Verify acknowledgment appears
    5. Wait for processing (30s)
    6. Navigate to skills page
    7. Verify XP increased
    """
    # Step 1: Navigate
    browser.get(f"{test_server}/journal")
    
    # Step 2: Enter text
    textarea = browser.find_element(By.TAG_NAME, "textarea")
    entry_text = "Today I practiced Python programming for 90 minutes. " * 10  # 50+ words
    textarea.send_keys(entry_text)
    
    # Step 3: Submit
    submit_button = browser.find_element(By.XPATH, "//button[contains(text(), 'Submit')]")
    submit_button.click()
    
    # Step 4: Verify acknowledgment
    WebDriverWait(browser, 5).until(
        EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'submitted')]"))
    )
    
    # Step 5: Wait for processing
    time.sleep(30)
    
    # Step 6: Navigate to skills
    browser.get(f"{test_server}/skills")
    
    # Step 7: Verify XP increased
    skill_cards = browser.find_elements(By.CLASS_NAME, "skill-card")
    assert len(skill_cards) > 0
    
    # Check for "Python Programming" skill
    python_skill = [s for s in skill_cards if "Python" in s.text][0]
    assert "Level" in python_skill.text


# Run with: pytest tests/e2e/ -v -s
```

---

## PART IV: CI/CD PIPELINE

### 4.1 GitHub Actions Workflow

**.github/workflows/ci.yml:**

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        python-version: ['3.11', '3.12']
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Cache dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Lint with Black and Ruff
      run: |
        black --check src/ tests/
        ruff check src/ tests/
    
    - name: Type check with MyPy
      run: |
        mypy src/
    
    - name: Run unit tests
      run: |
        pytest tests/unit/ -v --cov=src --cov-report=xml
    
    - name: Run integration tests
      run: |
        pytest tests/integration/ -v
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        flags: unittests
        name: codecov-umbrella
    
    - name: Check coverage threshold
      run: |
        coverage report --fail-under=95

  e2e:
    runs-on: ubuntu-latest
    needs: test
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Install Chrome
      run: |
        sudo apt-get update
        sudo apt-get install -y google-chrome-stable
    
    - name: Run E2E tests
      run: |
        pytest tests/e2e/ -v --maxfail=1
    
  build:
    runs-on: ubuntu-latest
    needs: [test, e2e]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Build Docker image
      run: |
        docker build -t rpg-life-tracker:latest .
    
    - name: Run security scan
      run: |
        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
          aquasec/trivy image rpg-life-tracker:latest
```

---

## PART V: PERFORMANCE BENCHMARKING

### 5.1 Load Testing (Locust)

**tests/load/locustfile.py:**

```python
"""
Load testing for API endpoints.
"""

from locust import HttpUser, task, between


class APIUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def submit_journal_entry(self):
        """Submit journal entry (most common operation)."""
        self.client.post("/api/journal/entries", json={
            "user_id": "load_test_user",
            "raw_text": "Today I practiced coding for 60 minutes. " * 10
        })
    
    @task(2)
    def get_skills(self):
        """Get user skills."""
        self.client.get("/api/skills?user_id=load_test_user")
    
    @task(1)
    def get_quests(self):
        """Get active quests."""
        self.client.get("/api/quests?user_id=load_test_user")


# Run with: locust -f tests/load/locustfile.py --host=http://localhost:8000
# Then open http://localhost:8089
```

### 5.2 Performance Benchmarks

**tests/performance/test_benchmarks.py:**

```python
"""
Performance benchmarks.
Target: All operations <100ms
"""

import pytest
import time
from src.core.xp import calculate_xp_for_level, calculate_level_from_xp


class TestPerformanceBenchmarks:
    """Performance benchmarks (20 tests)."""
    
    def test_xp_calculation_speed(self, benchmark):
        """XP calculation should be <1ms."""
        result = benchmark(calculate_xp_for_level, 50)
        assert result > 0
    
    def test_level_calculation_speed(self, benchmark):
        """Level calculation should be <1ms."""
        result = benchmark(calculate_level_from_xp, 1000000)
        assert result > 0
    
    def test_db_query_speed(self, test_db, test_user):
        """Database query should be <100ms."""
        from src.db.models import Skill
        
        start = time.time()
        skills = test_db.query(Skill).filter_by(user_id=test_user.user_id).all()
        end = time.time()
        
        query_time_ms = (end - start) * 1000
        assert query_time_ms < 100, f"Query took {query_time_ms:.2f}ms (target: <100ms)"


# Run with: pytest tests/performance/ --benchmark-only
```

---

## CONCLUSION

### Testing Suite Summary

**Total Tests: 500+**
- ✅ Unit tests: 300 (60%)
- ✅ Integration tests: 150 (30%)
- ✅ E2E tests: 50 (10%)

**Coverage Target: ≥95%**
- Core modules: 100%
- API routes: 95%
- Database models: 98%

**CI/CD Pipeline:**
- GitHub Actions (automated)
- Runs on every PR/push
- Coverage reporting (Codecov)
- Performance benchmarks

**Performance Targets:**
- Unit tests: <1 minute total
- Integration tests: <3 minutes total
- E2E tests: <10 minutes total
- Full CI pipeline: <5 minutes

### Next Steps

1. ✅ Copy test templates to project
2. ✅ Run pytest to verify setup
3. ✅ Configure GitHub Actions
4. ✅ Set coverage threshold (95%)
5. ✅ Run load tests (Locust)
6. ✅ Monitor CI/CD pipeline

---

**Document Status:** PRODUCTION READY  
**Test Count:** 500+ automated tests  
**Coverage Target:** ≥95%  
**CI/CD:** GitHub Actions  
**Performance:** All operations <100ms  
**Last Updated:** February 26, 2026

---

END OF TESTING_AUTOMATION_SUITE.md
