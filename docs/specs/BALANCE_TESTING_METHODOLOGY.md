# BALANCE_TESTING_METHODOLOGY.md
**Project:** RPG Life Tracker - Balance Testing Framework  
**Version:** 1.0  
**Date:** February 26, 2026  
**Status:** PRODUCTION READY  
**Purpose:** Comprehensive testing framework for validating and maintaining system balance

---

## EXECUTIVE SUMMARY

### Document Purpose

This document establishes the **testing methodology** for ensuring the RPG Life Tracker system remains balanced, fair, and motivating throughout development and operation. It provides:

- Automated test suites (unit, integration, property-based)
- Manual validation procedures (playtesting, expert review)
- Continuous monitoring frameworks (production metrics, A/B testing)
- Balance adjustment protocols (when and how to rebalance)

**Core Principle:** *Balance is not a one-time achievement but an ongoing process. Test continuously, measure rigorously, adjust carefully.*

### Key Testing Objectives

**1. Progression Balance**
- ✅ Level 30 achievable in 90 days (dedicated users)
- ✅ Level 19 achievable in 90 days (casual users)
- ✅ No user feels "stuck" or "bored" due to poor pacing

**2. Theme Correlation**
- ✅ Themes progress 1000× slower than skills (0.1% XP propagation)
- ✅ R² > 0.90 correlation between skill and theme progression
- ✅ No themes "race ahead" or "fall behind" unexpectedly

**3. Variety Bonus Effectiveness**
- ✅ 0-60% range encourages exploration
- ✅ Shannon entropy > 0.60 for balanced players
- ✅ Variety bonus doesn't dominate progression (<30% of total XP)

**4. Failure Recovery**
- ✅ Graduated penalties (0%/-20%/-50%) allow learning
- ✅ Struggle Arc triggers after 3 failures (not before)
- ✅ Users recover from failures within 7-14 days

**5. Troll Multiplier Fairness**
- ✅ 1.0×-5.0× range rewards creativity
- ✅ Anomaly score (0-10) is transparent and auditable
- ✅ Gaming attempts capped (no 10× exploits)

**6. No Game-Breaking Exploits**
- ✅ Min-maxing attempts identified and mitigated
- ✅ Edge cases handled gracefully
- ✅ System remains fair for all play styles

### Testing Philosophy

**1. Balance vs. Fun Trade-Offs**
- Perfect mathematical balance ≠ fun gameplay
- Accept small imbalances if they increase enjoyment
- Example: Troll multiplier 5.0× is "overpowered" but motivates creativity

**2. Evidence-Based Adjustments**
- Never adjust based on "gut feeling"
- Require statistical significance (p < 0.05)
- Collect ≥100 data points before rebalancing

**3. Gradual Changes**
- No drastic rebalancing (±20% maximum per adjustment)
- Test changes in staging before production
- Communicate changes transparently to users

**4. User Agency Preservation**
- Balance adjustments must not punish existing players
- Grandfather existing progress if rules change significantly
- Provide opt-in for experimental balance changes

---

## PART I: AUTOMATED TESTING FRAMEWORK

### 1.1 Unit Tests (Formula Correctness)

**Purpose:** Verify individual formulas produce expected outputs

**Framework:** pytest with parametrize for extensive test coverage

**Test Categories:**

#### 1.1.1 XP Calculation Tests

```python
import pytest
from rpg_life_tracker.xp import calculate_xp_for_level, calculate_theme_xp

class TestXPCalculation:
    """Test XP curve formulas (Section 3, Appendix A)"""
    
    @pytest.mark.parametrize("level,expected_xp", [
        (1, 480),      # Base XP
        (5, 5093),     # Early progression
        (10, 22800),   # Mid progression
        (30, 296227),  # Target (90 days)
        (50, 1013776), # Advanced
        (100, 5765760) # Maximum
    ])
    def test_xp_requirements(self, level: int, expected_xp: int):
        """Verify XP requirements match Appendix A.1 table"""
        calculated = calculate_xp_for_level(level)
        assert abs(calculated - expected_xp) < 10, \
            f"Level {level}: Expected {expected_xp}, got {calculated}"
    
    @pytest.mark.parametrize("rank,expected_exponent", [
        ("F", 1.5), ("D", 1.5), ("C", 1.5), ("B", 1.5), ("A", 1.5),
        ("S", 1.6), ("SS", 1.8), ("SSS", 2.0)
    ])
    def test_rank_exponents(self, rank: str, expected_exponent: float):
        """Verify progressive difficulty (Section 3.2.3)"""
        exponent = get_exponent_for_rank(rank)
        assert exponent == expected_exponent
    
    def test_theme_xp_propagation(self):
        """Verify 0.1% theme XP (Q22 EXTRA)"""
        skill_xp = 695000  # Level 30 skill
        theme_xp = calculate_theme_xp(skill_xp)
        
        # Expected: 695 (0.1% of 695000)
        assert theme_xp == 695, f"Expected 695, got {theme_xp}"
        
        # Verify theme level ~3 when skill level 30
        theme_level = calculate_level_from_xp(theme_xp)
        assert 2 <= theme_level <= 4, \
            f"Expected theme level 2-4, got {theme_level}"
```

#### 1.1.2 Variety Bonus Tests

```python
class TestVarietyBonus:
    """Test balance variety bonus (Section 5)"""
    
    @pytest.mark.parametrize("strategy_count,expected_range", [
        (1, (0.00, 0.10)),  # No variety
        (3, (0.20, 0.35)),  # Some variety
        (6, (0.50, 0.60))   # Maximum variety
    ])
    def test_variety_bonus_ranges(self, strategy_count: int, expected_range: tuple):
        """Verify 0-60% variety bonus range (Section 5.4)"""
        activities = create_balanced_activities(strategy_count)
        bonus = calculate_variety_bonus(activities, window_days=30)
        
        min_expected, max_expected = expected_range
        assert min_expected <= bonus <= max_expected, \
            f"{strategy_count} strategies: Expected {expected_range}, got {bonus}"
    
    def test_shannon_entropy_calculation(self):
        """Verify Shannon entropy formula (Section 5.3)"""
        # Equal distribution across 6 strategies
        activities = {
            "Study Burst": 10,
            "Productive Morning": 10,
            "Troll Exploits": 10,
            "Hyperfocus Session": 10,
            "Balanced Day": 10,
            "Learning Streak": 10
        }
        
        entropy = calculate_shannon_entropy(activities)
        
        # Perfect balance: entropy = log2(6) = 2.585
        assert 2.50 <= entropy <= 2.65, \
            f"Expected ~2.585, got {entropy}"
```

#### 1.1.3 Failure Penalty Tests

```python
class TestFailurePenalties:
    """Test failure system (Q23, Section 10.7)"""
    
    @pytest.mark.parametrize("failure_count,expected_penalty", [
        (1, 0.00),   # 1st failure: 0% penalty
        (2, 0.20),   # 2nd failure: -20% XP
        (3, 0.50),   # 3rd+ failure: -50% XP
        (5, 0.50)    # Cap at -50%
    ])
    def test_graduated_penalties(self, failure_count: int, expected_penalty: float):
        """Verify graduated failure penalties"""
        penalty = calculate_failure_penalty(failure_count)
        assert penalty == expected_penalty
    
    def test_struggle_arc_trigger(self):
        """Verify Struggle Arc triggers on 3rd failure (Q24)"""
        tracker = FailureTracker(user_id="test", skill_id="skill_123")
        
        # 1st failure: no arc
        tracker.record_failure(quest_id="q1")
        assert not tracker.should_trigger_struggle_arc()
        
        # 2nd failure: no arc
        tracker.record_failure(quest_id="q2")
        assert not tracker.should_trigger_struggle_arc()
        
        # 3rd failure: TRIGGER
        tracker.record_failure(quest_id="q3")
        assert tracker.should_trigger_struggle_arc()
```

#### 1.1.4 Troll Multiplier Tests

```python
class TestTrollMultiplier:
    """Test anomaly detection and troll multiplier (Section 9)"""
    
    @pytest.mark.parametrize("anomaly_score,expected_mult", [
        (0.0, 1.0),   # Normal activity
        (5.0, 2.19),  # Moderate creativity
        (10.0, 5.0)   # Maximum creativity
    ])
    def test_troll_multiplier_formula(self, anomaly_score: float, expected_mult: float):
        """Verify 1.0×-5.0× troll multiplier (Section 9.3)"""
        mult = calculate_troll_multiplier(anomaly_score)
        assert abs(mult - expected_mult) < 0.05
    
    def test_anomaly_score_components(self):
        """Verify 0-10 anomaly scoring (Section 9.2)"""
        entry = {
            "novelty_score": 3.0,      # Not seen in 90 days
            "complexity_score": 2.0,   # Multi-skill, long duration
            "creativity_score": 3.0,   # AI assessment
            "efficiency_score": 2.0    # Clever solution
        }
        
        total = calculate_anomaly_score(entry)
        assert total == 10.0, f"Expected 10.0, got {total}"
```

**Coverage Target:** ≥95% for all formula modules

**CI Integration:** Run on every pull request, block merge if <95%

---

### 1.2 Integration Tests (System Interactions)

**Purpose:** Verify systems work together correctly

**Test Scenarios:**

#### 1.2.1 XP Flow Integration

```python
class TestXPFlowIntegration:
    """Test end-to-end XP calculation through all systems"""
    
    def test_complete_xp_pipeline(self, db_session):
        """
        Test: Journal entry → Skill XP → Theme XP → Level up
        
        Scenario:
        - User writes entry (60 min Python coding)
        - Quest matched (Coding Session, 1.0× base)
        - Quality multiplier 1.2× (focused practice)
        - Variety bonus 0.30 (balanced week)
        - Expected: 1123 XP to skill, 1 XP to theme
        """
        user = create_test_user(id="user_123")
        
        # Submit entry
        entry = JournalEntry(
            user_id="user_123",
            content="Worked on Python backend for 60 minutes. "
                    "Implemented user authentication with JWT tokens."
        )
        
        # Process through pipeline
        result = process_entry(entry, db_session)
        
        # Verify skill XP
        skill = db_session.query(Skill).filter_by(
            user_id="user_123",
            canonical_name="Python Programming"
        ).first()
        
        expected_xp = 480 * 2.0 * 1.2 * 1.3  # base * time * quality * variety
        assert abs(skill.total_xp - expected_xp) < 50
        
        # Verify theme XP (0.1% propagation)
        theme = db_session.query(Theme).filter_by(
            user_id="user_123",
            name="Professional"
        ).first()
        
        expected_theme_xp = max(1, int(expected_xp * 0.001))
        assert theme.total_xp == expected_theme_xp
```

#### 1.2.2 Forgiveness System Integration

```python
def test_forgiveness_decay_integration(self, db_session):
    """
    Test: Skill staleness → Decay → Forgiveness protection
    
    Scenario:
    - User has level 10 skill (23280 XP)
    - 30 days of inactivity
    - Balanced forgiveness preset (decay_rate=0.05)
    - Expected: 75% XP retained (grace period + slow decay)
    """
    user = create_test_user(forgiveness_preset="balanced")
    skill = create_test_skill(user_id=user.id, level=10)
    
    # Simulate 30 days of inactivity
    simulate_days_passing(30, db_session)
    
    # Calculate decay
    apply_forgiveness_decay(user.id, db_session)
    
    db_session.refresh(skill)
    retained_pct = skill.total_xp / 23280
    
    assert 0.70 <= retained_pct <= 0.80, \
        f"Expected 70-80% retention, got {retained_pct:.2%}"
```

#### 1.2.3 Story Arc XP Modifiers

```python
def test_story_arc_xp_modifiers(self, db_session):
    """
    Test: Story arc active → XP modifiers apply
    
    Scenario:
    - User in Tutorial Arc (1.5× XP for all)
    - Complete quest: 1000 base XP
    - Expected: 1500 XP awarded
    """
    user = create_test_user()
    arc = activate_story_arc(user.id, arc_type="tutorial", db_session)
    
    quest = create_test_quest(base_xp=1000)
    award_xp_for_quest(user.id, quest.id, db_session)
    
    skill = get_quest_skill(quest.id, db_session)
    assert skill.total_xp == 1500, \
        f"Expected 1500 XP (1.5× Tutorial), got {skill.total_xp}"
```

**Coverage Target:** ≥80% for integration paths

---

### 1.3 Property-Based Tests (Hypothesis Framework)

**Purpose:** Test system behavior across wide parameter ranges

**Framework:** pytest-hypothesis for automated test case generation

#### 1.3.1 XP Curve Properties

```python
from hypothesis import given, strategies as st

class TestXPCurveProperties:
    """Property-based tests for XP curve invariants"""
    
    @given(level=st.integers(min_value=1, max_value=100))
    def test_xp_always_increases(self, level):
        """Property: XP required for level N+1 > level N"""
        xp_current = calculate_xp_for_level(level)
        xp_next = calculate_xp_for_level(level + 1)
        
        assert xp_next > xp_current, \
            f"Level {level+1} XP must be higher than level {level}"
    
    @given(
        xp=st.integers(min_value=1, max_value=10000000),
        additional_xp=st.integers(min_value=1, max_value=100000)
    )
    def test_level_never_decreases(self, xp, additional_xp):
        """Property: Adding XP never decreases level"""
        level_before = calculate_level_from_xp(xp)
        level_after = calculate_level_from_xp(xp + additional_xp)
        
        assert level_after >= level_before
    
    @given(skill_xp=st.integers(min_value=1, max_value=10000000))
    def test_theme_xp_always_lower(self, skill_xp):
        """Property: Theme XP always ≤ 0.1% of skill XP"""
        theme_xp = calculate_theme_xp(skill_xp)
        max_theme_xp = int(skill_xp * 0.001)
        
        assert theme_xp <= max_theme_xp
        assert theme_xp >= 1  # Minimum 1 XP
```

#### 1.3.2 Balance Variety Properties

```python
@given(
    activities=st.dictionaries(
        keys=st.sampled_from([
            "Study Burst", "Productive Morning", "Troll Exploits",
            "Hyperfocus Session", "Balanced Day", "Learning Streak"
        ]),
        values=st.integers(min_value=1, max_value=100),
        min_size=1,
        max_size=6
    )
)
def test_variety_bonus_bounds(self, activities):
    """Property: Variety bonus always 0-60%"""
    bonus = calculate_variety_bonus(activities, window_days=30)
    
    assert 0.0 <= bonus <= 0.60, \
        f"Variety bonus out of bounds: {bonus}"

@given(
    strategy_count=st.integers(min_value=1, max_value=6)
)
def test_more_strategies_higher_bonus(self, strategy_count):
    """Property: More strategies → higher variety bonus"""
    # Create equal distribution
    activities_few = create_balanced_activities(strategy_count - 1 if strategy_count > 1 else 1)
    activities_many = create_balanced_activities(strategy_count)
    
    bonus_few = calculate_variety_bonus(activities_few, window_days=30)
    bonus_many = calculate_variety_bonus(activities_many, window_days=30)
    
    if strategy_count > 1:
        assert bonus_many >= bonus_few
```

**Property Categories:**
- **Monotonicity:** Progression always increases (never decreases)
- **Bounds:** Values stay within defined ranges (0-60%, 1.0×-5.0×)
- **Symmetry:** Order of operations doesn't affect results
- **Idempotency:** Repeated calculations yield same result

**Run Frequency:** 100 examples per property test (Hypothesis default)

---

### 1.4 Regression Tests (Balance Preservation)

**Purpose:** Ensure balance changes don't break existing systems

**Test Strategy:**

#### 1.4.1 Snapshot Testing

```python
class TestBalanceSnapshots:
    """Regression tests using snapshot testing"""
    
    def test_90_day_progression_snapshot(self, snapshot):
        """
        Baseline: Marcus persona (dedicated user)
        Expected: Level 31 in 90 days
        
        If this test fails after a change, balance has shifted.
        Decide: Is the shift intentional? Update snapshot if yes.
        """
        marcus = simulate_user_persona("Marcus", days=90)
        
        snapshot.assert_match({
            "final_level": marcus.level,
            "total_xp": marcus.total_xp,
            "themes": {t.name: t.level for t in marcus.themes}
        })
    
    def test_theme_correlation_snapshot(self, snapshot):
        """
        Baseline: Theme XP correlates with skill XP (R² > 0.90)
        """
        user = simulate_balanced_user(days=90)
        correlation = calculate_theme_skill_correlation(user)
        
        snapshot.assert_match({
            "r_squared": round(correlation["r_squared"], 3),
            "expected_minimum": 0.90
        })
        
        assert correlation["r_squared"] >= 0.90
```

#### 1.4.2 Golden Master Testing

```python
def test_xp_calculation_golden_master():
    """
    Golden Master: Known-good XP calculation
    
    Input: 60 min Python coding, quality 1.2×, variety 0.30
    Output: 1123 XP to skill, 1 XP to theme
    
    This is the "golden master" - any deviation requires review.
    """
    result = calculate_xp(
        base_xp=480,
        minutes=60,
        quality_mult=1.2,
        variety_bonus=0.30
    )
    
    assert result["skill_xp"] == 1123
    assert result["theme_xp"] == 1
```

**Snapshot Updates:** Require manual review + approval

**Regression Detection:** Compare snapshots on every major change

---

## PART II: MANUAL VALIDATION PROCEDURES

### 2.1 Playtesting Protocols

**Purpose:** Human validation of balance through real gameplay

**Test Phases:**

#### 2.1.1 Alpha Playtesting (Internal, 2-4 weeks)

**Participants:** 5-10 team members + friends

**Objectives:**
- Identify game-breaking bugs
- Validate core progression loop
- Test forgiveness mechanics (do users feel punished?)
- Gather qualitative feedback (fun factor, motivation)

**Procedure:**
1. Each tester creates account, chooses personality
2. Use system for 2-4 weeks (minimum 20 entries)
3. Complete feedback survey (Likert scale + open-ended)
4. Track: Entries per day, quests completed, level reached
5. Exit interview (30 min, structured questions)

**Key Questions:**
- "Did you feel progression was too slow or too fast?"
- "Did failures feel punishing or forgiving?"
- "Did variety bonus motivate you to try new activities?"
- "Would you continue using this system after the test?"

**Success Criteria:**
- 80% of testers reach level 5+ in 2 weeks
- 70% report "fun" or "very fun" (Likert ≥4/5)
- 60% would continue using after test

#### 2.1.2 Beta Playtesting (External, 6-8 weeks)

**Participants:** 50-100 volunteers (recruit via Reddit, Discord, forums)

**Objectives:**
- Validate balance at scale
- Identify edge cases missed in alpha
- Test multi-user installations
- Gather demographic data (casual vs. dedicated users)

**Procedure:**
1. Recruit diverse user base (age, occupation, play style)
2. Randomize forgiveness presets (balanced, hardcore, lenient)
3. Track all metrics (XP, levels, quests, variety, failures)
4. Weekly surveys (5 min, track motivation trends)
5. Final survey (10 min, overall satisfaction)

**Success Criteria:**
- 50% retention at 4 weeks (still using system)
- Level 10+ achieved by 60% of dedicated users
- Level 5+ achieved by 40% of casual users
- No game-breaking exploits discovered
- 70% satisfaction score (Likert ≥4/5)

---

### 2.2 Expert Review (Domain Specialists)

**Purpose:** Validate calibration with domain experts

**Experts Needed:**
- Learning scientist (PhD in education/psychology)
- Game designer (5+ years AAA or indie experience)
- UX researcher (specializing in motivation/engagement)

**Review Areas:**

#### 2.2.1 Learning Science Review

**Expert Validates:**
- XP calibration (time-to-proficiency research-backed?)
- Difficulty scaling (ZPD principles applied correctly?)
- Forgiveness mechanics (aligned with growth mindset research?)
- Spaced repetition (decay rates realistic?)

**Deliverable:** Written report with Grade A/B/C for each area

#### 2.2.2 Game Design Review

**Expert Validates:**
- Progression pacing (too fast? too slow? just right?)
- Variety bonus (encourages exploration vs. dominates meta?)
- Troll multiplier (fun vs. exploitable?)
- Failure system (forgiving vs. toothless?)

**Deliverable:** Design critique with specific recommendations

#### 2.2.3 UX Research Review

**Expert Validates:**
- User motivation (intrinsic vs. extrinsic balance?)
- Engagement loops (daily habits formed?)
- Frustration points (where do users give up?)
- Delight moments (what feels rewarding?)

**Deliverable:** UX audit with user journey map

**Expert Compensation:** $500-$1000 per review (or open-source contribution credit)

---

## PART III: BALANCE METRICS & MONITORING

### 3.1 Key Performance Indicators (KPIs)

**Track Continuously in Production:**

#### 3.1.1 Progression Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| **Days to Level 10** | 30 days (dedicated) | <20 or >45 days |
| **Days to Level 30** | 90 days (dedicated) | <70 or >120 days |
| **Casual User Level (30 days)** | Level 5-7 | <3 or >10 |
| **Dropout Rate (30 days)** | <20% | >30% |
| **Average XP per Session** | 800-1200 | <500 or >2000 |

#### 3.1.2 Theme Correlation Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| **Theme-Skill R²** | >0.90 | <0.85 |
| **Theme Level Lag** | 1000× slower | <500× or >1500× |
| **Theme XP % of Skill XP** | ~0.1% | <0.05% or >0.2% |

#### 3.1.3 Variety Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| **Average Variety Bonus** | 20-40% | <10% or >50% |
| **Shannon Entropy** | >0.60 | <0.50 |
| **% Users with 4+ Strategies** | >60% | <40% |
| **Variety Bonus % of Total XP** | <30% | >40% |

#### 3.1.4 Failure Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| **Quest Success Rate** | 70-80% | <60% or >90% |
| **Average Failures per Skill** | 1-2 | >5 |
| **Struggle Arc Trigger Rate** | 10-20% of users | <5% or >30% |
| **Recovery Time (failure→success)** | 7-14 days | >30 days |

### 3.2 Monitoring Dashboard

**Tool:** Grafana + Prometheus (open-source metrics)

**Dashboard Sections:**

1. **Progression Overview**
   - Average level by days active (line chart)
   - XP distribution histogram
   - Level-up events per day (bar chart)

2. **Theme Correlation**
   - Scatter plot: Skill level vs. Theme level
   - R² trend over time
   - Theme lag factor (target: 1000×)

3. **Balance Variety**
   - Strategy distribution (pie chart)
   - Variety bonus histogram
   - Shannon entropy trend

4. **Failure Analysis**
   - Success/failure rates by quest type
   - Struggle Arc triggers per week
   - Recovery time distribution

5. **User Segmentation**
   - Casual vs. Dedicated vs. Hyperfocus
   - Forgiveness preset usage
   - Personality distribution

**Alert Configuration:**
- Email alerts for critical thresholds (>30% deviation)
- Slack alerts for warnings (>20% deviation)
- Weekly summary reports (CSV + charts)

---

### 3.3 A/B Testing Framework (Post-MVP)

**Purpose:** Test balance changes on subset of users

**Example A/B Tests:**

#### Test 1: Variety Bonus Range

**Hypothesis:** Increasing variety bonus to 0-80% will increase strategy diversity

**Groups:**
- **Control (A):** 0-60% variety bonus (current)
- **Treatment (B):** 0-80% variety bonus (proposed)

**Sample Size:** 500 users per group (1000 total)

**Duration:** 30 days

**Metrics:**
- Primary: Shannon entropy (strategy diversity)
- Secondary: XP per session, dropout rate, satisfaction score

**Decision Criteria:**
- If Shannon entropy increases by >10% (p<0.05) → Deploy to all
- If dropout rate increases by >5% → Reject change
- Otherwise → Inconclusive, need more data

#### Test 2: Failure Penalty Adjustment

**Hypothesis:** Reducing 3rd failure penalty to -40% (from -50%) will reduce dropout

**Groups:**
- **Control (A):** 0%/-20%/-50% (current)
- **Treatment (B):** 0%/-20%/-40% (proposed)

**Sample Size:** 1000 users per group (2000 total)

**Duration:** 60 days

**Metrics:**
- Primary: Dropout rate after 3 failures
- Secondary: Recovery time, satisfaction score, Struggle Arc completion rate

**Decision Criteria:**
- If dropout reduces by >20% (p<0.05) → Deploy
- If Struggle Arc completion drops by >30% → Reject (too easy)
- Otherwise → Iterate design

**A/B Testing Infrastructure:**
- Feature flags (LaunchDarkly or self-hosted)
- User assignment (hash user_id for consistent grouping)
- Statistical analysis (Python scipy.stats, R)

---

## PART IV: BALANCE ADJUSTMENT PROTOCOLS

### 4.1 When to Rebalance

**Trigger Conditions:**

1. **Critical Imbalance Detected**
   - Metric exceeds alert threshold for 7+ days
   - Example: Theme lag factor <500× or >1500×
   - **Action:** Emergency hotfix within 48 hours

2. **Sustained Drift**
   - Metric trends away from target for 30+ days
   - Example: Average variety bonus drops from 30% to 15%
   - **Action:** Scheduled rebalance in next release

3. **User Feedback Consensus**
   - 30%+ of beta testers report same issue
   - Example: "Variety bonus feels too weak"
   - **Action:** Investigate, run A/B test if validated

4. **New Research Published**
   - Learning science research contradicts current calibration
   - Example: Spaced repetition decay rate should be 0.08 (not 0.05)
   - **Action:** Update KB Research Foundation, recalibrate

**Non-Triggers (DO NOT Rebalance):**
- Single user complaint (outlier)
- Metric within target range (even if low end)
- Personal preference ("I prefer faster progression")
- Short-term variance (<7 days)

### 4.2 Rebalancing Process

**Step 1: Identify Problem**
- Document metric deviation with data
- Hypothesize root cause (formula bug? design flaw? user behavior shift?)

**Step 2: Propose Solution**
- Small adjustments (±10-20% parameter changes)
- Example: Variety bonus max 60% → 70%

**Step 3: Simulate Impact**
- Run Q21-Q40 simulation with new parameters
- Verify: Does this fix the problem without breaking others?

**Step 4: A/B Test (if major change)**
- Test on 10-20% of users
- Duration: 30-60 days
- Statistical significance: p<0.05

**Step 5: Deploy & Monitor**
- Gradual rollout (10% → 50% → 100% over 1 week)
- Monitor dashboard hourly for first 48 hours
- Rollback plan ready (feature flag)

**Step 6: Communicate**
- Changelog entry explaining change
- Email active users (opt-in)
- Reddit/Discord announcement

**Step 7: Document**
- Update architecture docs
- Update KB Research Foundation if relevant
- Record in decision log (Appendix G)

### 4.3 Rollback Criteria

**Immediate Rollback If:**
- Critical bug introduced (data loss, crashes)
- Metric swings >50% from target
- User satisfaction drops >20%
- Exploit discovered (game-breaking)

**Gradual Rollback If:**
- A/B test shows no significant improvement
- User feedback overwhelmingly negative
- Unintended side effects (e.g., variety bonus too strong, now dominates)

---

## PART V: TEST SCENARIOS CATALOG

### 5.1 XP System Scenarios

**Scenario 1: Rapid Leveling (Edge Case)**
- **Setup:** User completes 10 quests per day for 30 days
- **Expected:** Level ~25-30 (not level 50+)
- **Validates:** XP curve prevents hyper-leveling

**Scenario 2: Theme Lag Validation**
- **Setup:** User reaches skill level 50 (1,013,776 XP)
- **Expected:** Theme level ~5-7 (1,013 XP)
- **Validates:** 0.1% propagation (1000× slower)

**Scenario 3: Multi-Skill Quest XP**
- **Setup:** Quest requires 3 skills (weights: 0.5, 0.3, 0.2)
- **Expected:** Primary gets 100% XP, others get weighted XP
- **Validates:** Q22 multi-skill distribution

### 5.2 Variety Scenarios

**Scenario 4: No Variety (Single Strategy)**
- **Setup:** User only does "Study Burst" for 30 days
- **Expected:** Variety bonus ~0-5%
- **Validates:** Low variety = low bonus

**Scenario 5: Perfect Balance (6 Strategies)**
- **Setup:** User does all 6 strategies equally for 30 days
- **Expected:** Variety bonus ~50-60%
- **Validates:** High variety = high bonus

**Scenario 6: Variety Doesn't Dominate**
- **Setup:** Track variety bonus % of total XP
- **Expected:** Variety bonus <30% of total
- **Validates:** Variety enhances, doesn't replace core progression

### 5.3 Failure Scenarios

**Scenario 7: Graduated Penalties**
- **Setup:** User fails same quest 3 times
- **Expected:** 0% → -20% → -50% XP penalties
- **Validates:** Q23 failure system

**Scenario 8: Struggle Arc Trigger**
- **Setup:** User fails 3 quests on same skill
- **Expected:** Struggle Arc invitation appears
- **Validates:** Q24 arc trigger

**Scenario 9: Failure Recovery**
- **Setup:** User fails 2 times, then succeeds
- **Expected:** Failure count resets, full XP awarded
- **Validates:** Recovery mechanic works

### 5.4 Troll Multiplier Scenarios

**Scenario 10: Normal Activity**
- **Setup:** Standard journal entry, no novelty
- **Expected:** Anomaly score ~0-2, multiplier ~1.0-1.3×
- **Validates:** Normal activity = normal XP

**Scenario 11: Creative Solution**
- **Setup:** Novel approach, high complexity
- **Expected:** Anomaly score ~7-9, multiplier ~3.5-4.5×
- **Validates:** Creativity rewarded

**Scenario 12: Maximum Creativity**
- **Setup:** AI rates entry 10/10 on all dimensions
- **Expected:** Anomaly score = 10, multiplier = 5.0×
- **Validates:** Cap prevents >5.0× exploits

### 5.5 Story Arc Scenarios

**Scenario 13: Tutorial Arc XP Boost**
- **Setup:** User in Tutorial Arc completes quest
- **Expected:** 1.5× XP awarded
- **Validates:** Q25 Tutorial modifier

**Scenario 14: Regression Arc XP Reduction**
- **Setup:** User in Regression Arc progresses
- **Expected:** Skills paused, Insights -50%
- **Validates:** Q25 Regression penalties

### 5.6 Learning System Scenarios

**Scenario 15: Q27 Training Phase**
- **Setup:** First 10 quests, user answers "yes" 8 times
- **Expected:** Bias = +0.12 toward "yes"
- **Validates:** Q27 10-quest training

**Scenario 16: Q27 Auto-Decision**
- **Setup:** After training, confidence = 0.60, bias = +0.15
- **Expected:** Auto-create quest (0.60 + 0.15 = 0.75 ≥ 0.65)
- **Validates:** Q27 auto-decision threshold

**Scenario 17: Q28 Streak Detection**
- **Setup:** User does "Daily Run" 3 days in a row
- **Expected:** AI predicts 70%+ confidence, auto-create streak quest
- **Validates:** Q28 streak auto-creation

---

## PART VI: CONTINUOUS IMPROVEMENT

### 6.1 Feedback Loops

**User Feedback Channels:**
- In-app feedback button (bug reports, feature requests)
- Monthly surveys (satisfaction, pain points)
- Discord community (discussions, suggestions)
- Reddit r/RPGLifeTracker (user-generated content)

**Developer Feedback:**
- Weekly team retrospectives (what's working, what's not)
- Quarterly balance reviews (metrics deep dive)
- Annual architecture audits (major redesign if needed)

### 6.2 Research Updates

**Stay Current:**
- Quarterly literature review (new research in learning science, motivation)
- Update KB Research Foundation with new citations
- Recalibrate XP/difficulty if new evidence contradicts current design

**Example:** If new meta-analysis shows spaced repetition decay rate should be 0.08 (not 0.05), update forgiveness system accordingly.

### 6.3 Evolutionary Balance

**Philosophy:** Balance is not static; it evolves as:
- Users get better at the system (meta-gaming)
- New strategies emerge (community discoveries)
- Research advances (better understanding of learning)

**Accept:** Small imbalances are inevitable and even desirable (keeps system dynamic)

**Reject:** Game-breaking exploits must be fixed immediately

---

## CONCLUSION

### Testing Lifecycle Summary

**Pre-Launch:**
1. ✅ Run automated test suite (unit, integration, property-based)
2. ✅ Alpha playtest (2-4 weeks, internal)
3. ✅ Expert review (learning scientist, game designer, UX)
4. ✅ Beta playtest (6-8 weeks, 50-100 users)
5. ✅ Final simulation validation

**Post-Launch:**
1. ✅ Monitor metrics dashboard (daily)
2. ✅ Collect user feedback (weekly)
3. ✅ Run regression tests (on every release)
4. ✅ A/B test major changes (30-60 days)
5. ✅ Quarterly balance reviews
6. ✅ Annual architecture audits

### Success Criteria

**System is Balanced If:**
- ✅ 90%+ of automated tests pass
- ✅ Alpha testers report 70%+ satisfaction
- ✅ Beta testers achieve target progression (level 30 in 90 days)
- ✅ Metrics stay within alert thresholds (±20% of target)
- ✅ No critical exploits discovered
- ✅ User retention >50% at 30 days

### Ongoing Commitment

Balance testing is not a one-time task but a **continuous process**:
- Weekly: Monitor metrics, review user feedback
- Monthly: Analyze trends, identify drift
- Quarterly: Balance review meeting, research update
- Annually: Major architecture audit, rebalance if needed

**Core Principle:** Test rigorously, measure continuously, adjust carefully, communicate transparently.

---

**Document Status:** PRODUCTION READY  
**Automated Test Count:** 100+ (unit, integration, property)  
**Manual Test Scenarios:** 17 (cataloged)  
**KPIs Defined:** 20 metrics with alert thresholds  
**A/B Testing:** Framework ready (post-MVP)  
**Last Updated:** February 26, 2026  
**Next Review:** May 26, 2026

---

END OF BALANCE_TESTING_METHODOLOGY.md
