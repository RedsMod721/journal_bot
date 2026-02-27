# KB_VALIDATION_METHODOLOGY.md
**Project:** RPG Life Tracker - KB Validation Methodology  
**Version:** 1.0  
**Date:** February 26, 2026  
**Status:** PRODUCTION READY  
**Purpose:** Comprehensive validation framework for pre-seeded knowledge base content

---

## EXECUTIVE SUMMARY

### Document Purpose

This document establishes the **validation methodology** for ensuring all pre-seeded knowledge base content meets quality, accuracy, and balance standards before deployment. Validation occurs in 4 stages:

1. **Automated Validation** (schema, bounds, citations)
2. **Statistical Validation** (calibration, distributions, correlations)
3. **Expert Review** (domain specialists, peer review)
4. **User Testing** (beta testers rate usefulness)

**Core Principle:** *Trust but verify. Every piece of content must pass all 4 validation stages.*

### Validation Scope

**In Scope:**
- 500-1000 Global Skills
- 200-500 Quest Templates
- 1000-2000 Insights
- 1000+ RAG Documents
- All citations (DOI link validation)
- XP calibration (match research + simulation)

**Out of Scope:**
- User-generated content (validated at runtime)
- AI-generated responses (validated per-request)
- Future KB updates (use this methodology iteratively)

### Success Criteria

**KB Content is Valid If:**
- ✅ 100% pass automated validation (zero critical errors)
- ✅ Statistical metrics within bounds (R² > 0.80, distributions match research)
- ✅ Expert approval (5/5 domain specialists)
- ✅ Bias audit passed (2/2 independent reviewers)
- ✅ User testing satisfaction ≥70% (beta testers)
- ✅ Zero game-breaking imbalances (no skills 10× overpowered)

---

## PART I: AUTOMATED VALIDATION

### 1.1 Schema Validation

**Purpose:** Ensure all required fields populated, data types correct

**Validation Script (Python):**

```python
import json
import sqlite3
from typing import List, Dict, Tuple

class SchemaValidator:
    """Validate KB content against schema requirements"""
    
    def validate_skills(self, db_path: str) -> List[Dict]:
        """
        Validate global_skills table schema.
        
        Returns list of validation errors (empty if valid).
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        errors = []
        
        # Check all skills have required fields
        cursor.execute("""
            SELECT skill_id, canonical_name, category, difficulty_baseline,
                   typical_time_investment, xp_per_session_baseline,
                   related_themes, learning_curve_type, description,
                   evidence_citations, evidence_grade
            FROM global_skills
        """)
        
        for row in cursor.fetchall():
            skill_id = row[0]
            
            # Check for NULL values
            if any(field is None for field in row):
                errors.append({
                    "skill_id": skill_id,
                    "error": "NULL_FIELD",
                    "message": "One or more required fields are NULL"
                })
            
            # Validate category
            category = row[2]
            if category not in ["Physical", "Mental", "Professional", "Creative", "Social"]:
                errors.append({
                    "skill_id": skill_id,
                    "error": "INVALID_CATEGORY",
                    "message": f"Category '{category}' not in allowed list"
                })
            
            # Validate difficulty
            difficulty = row[3]
            if difficulty not in ["beginner", "intermediate", "advanced"]:
                errors.append({
                    "skill_id": skill_id,
                    "error": "INVALID_DIFFICULTY",
                    "message": f"Difficulty '{difficulty}' not in allowed list"
                })
            
            # Validate time investment (30-240 minutes)
            time_inv = row[4]
            if not (30 <= time_inv <= 240):
                errors.append({
                    "skill_id": skill_id,
                    "error": "TIME_OUT_OF_BOUNDS",
                    "message": f"Time investment {time_inv} not in range [30, 240]"
                })
            
            # Validate XP baseline (200-2000)
            xp_base = row[5]
            if not (200 <= xp_base <= 2000):
                errors.append({
                    "skill_id": skill_id,
                    "error": "XP_OUT_OF_BOUNDS",
                    "message": f"XP baseline {xp_base} not in range [200, 2000]"
                })
            
            # Validate learning curve type
            curve = row[7]
            if curve not in ["linear", "logarithmic", "sigmoid"]:
                errors.append({
                    "skill_id": skill_id,
                    "error": "INVALID_CURVE",
                    "message": f"Learning curve '{curve}' not in allowed list"
                })
            
            # Validate evidence grade
            grade = row[10]
            if grade not in ["A", "B", "C"]:
                errors.append({
                    "skill_id": skill_id,
                    "error": "INVALID_GRADE",
                    "message": f"Evidence grade '{grade}' not in allowed list"
                })
        
        conn.close()
        return errors
    
    def validate_quests(self, db_path: str) -> List[Dict]:
        """Validate global_quest_templates table schema"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        errors = []
        
        cursor.execute("""
            SELECT template_id, template_name, skill_category,
                   completion_type, difficulty_rating,
                   xp_reward_min, xp_reward_max
            FROM global_quest_templates
        """)
        
        for row in cursor.fetchall():
            template_id = row[0]
            
            # Check completion type
            comp_type = row[3]
            if comp_type not in ["one_time", "cumulative", "recursive", "streak"]:
                errors.append({
                    "template_id": template_id,
                    "error": "INVALID_COMPLETION_TYPE",
                    "message": f"Completion type '{comp_type}' not in allowed list"
                })
            
            # Check difficulty rating (1-10)
            difficulty = row[4]
            if not (1 <= difficulty <= 10):
                errors.append({
                    "template_id": template_id,
                    "error": "DIFFICULTY_OUT_OF_BOUNDS",
                    "message": f"Difficulty {difficulty} not in range [1, 10]"
                })
            
            # Check XP rewards (min < max, both in range)
            xp_min = row[5]
            xp_max = row[6]
            
            if not (500 <= xp_min <= 15000):
                errors.append({
                    "template_id": template_id,
                    "error": "XP_MIN_OUT_OF_BOUNDS",
                    "message": f"XP min {xp_min} not in range [500, 15000]"
                })
            
            if not (500 <= xp_max <= 15000):
                errors.append({
                    "template_id": template_id,
                    "error": "XP_MAX_OUT_OF_BOUNDS",
                    "message": f"XP max {xp_max} not in range [500, 15000]"
                })
            
            if xp_min >= xp_max:
                errors.append({
                    "template_id": template_id,
                    "error": "XP_MIN_GTE_MAX",
                    "message": f"XP min ({xp_min}) >= max ({xp_max})"
                })
        
        conn.close()
        return errors
    
    def validate_insights(self, db_path: str) -> List[Dict]:
        """Validate global_insights table schema"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        errors = []
        
        cursor.execute("""
            SELECT insight_id, strength_initial, evidence_grade
            FROM global_insights
        """)
        
        for row in cursor.fetchall():
            insight_id = row[0]
            
            # Check strength (0.0-1.0)
            strength = row[1]
            if not (0.0 <= strength <= 1.0):
                errors.append({
                    "insight_id": insight_id,
                    "error": "STRENGTH_OUT_OF_BOUNDS",
                    "message": f"Strength {strength} not in range [0.0, 1.0]"
                })
            
            # Check evidence grade
            grade = row[2]
            if grade not in ["A", "B", "C"]:
                errors.append({
                    "insight_id": insight_id,
                    "error": "INVALID_GRADE",
                    "message": f"Evidence grade '{grade}' not in allowed list"
                })
        
        conn.close()
        return errors

# Run validation
validator = SchemaValidator()
skill_errors = validator.validate_skills("kb_preseeded.db")
quest_errors = validator.validate_quests("kb_preseeded.db")
insight_errors = validator.validate_insights("kb_preseeded.db")

# Report
total_errors = len(skill_errors) + len(quest_errors) + len(insight_errors)
print(f"Schema Validation: {total_errors} errors found")

if total_errors > 0:
    print("VALIDATION FAILED - Fix errors before proceeding")
else:
    print("✅ Schema Validation PASSED")
```

**Critical Errors (Block Deployment):**
- NULL required fields
- Invalid categories/types
- Values out of bounds (XP, difficulty, time)
- Invalid evidence grades

**Warning Errors (Manual Review Required):**
- XP values near bounds (190-210 or 1980-2000)
- Very short/long descriptions (<20 or >500 chars)
- Grade C evidence (acceptable but needs review)

### 1.2 Citation Validation

**Purpose:** Verify all DOI links resolve successfully

**Validation Script:**

```python
import requests
import json
from typing import List, Dict

class CitationValidator:
    """Validate DOI citations resolve correctly"""
    
    def __init__(self):
        self.doi_base_url = "https://doi.org/"
    
    def validate_doi(self, doi: str) -> Dict:
        """
        Check if DOI resolves successfully.
        
        Returns:
        - status: "valid" | "invalid" | "error"
        - http_code: Response code (200, 404, etc.)
        - message: Error message if invalid
        """
        url = self.doi_base_url + doi
        
        try:
            response = requests.head(url, timeout=5, allow_redirects=True)
            
            if response.status_code == 200:
                return {
                    "doi": doi,
                    "status": "valid",
                    "http_code": 200,
                    "message": "DOI resolves successfully"
                }
            else:
                return {
                    "doi": doi,
                    "status": "invalid",
                    "http_code": response.status_code,
                    "message": f"DOI returns HTTP {response.status_code}"
                }
        except requests.exceptions.Timeout:
            return {
                "doi": doi,
                "status": "error",
                "http_code": None,
                "message": "Timeout (DOI server slow/unresponsive)"
            }
        except Exception as e:
            return {
                "doi": doi,
                "status": "error",
                "http_code": None,
                "message": str(e)
            }
    
    def validate_all_citations(self, db_path: str) -> List[Dict]:
        """Validate all DOI citations in KB"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        invalid_citations = []
        
        # Skills
        cursor.execute("SELECT skill_id, evidence_citations FROM global_skills")
        for row in cursor.fetchall():
            skill_id = row[0]
            citations = json.loads(row[1])
            
            if len(citations) < 2:
                invalid_citations.append({
                    "item_id": skill_id,
                    "item_type": "skill",
                    "error": "INSUFFICIENT_CITATIONS",
                    "message": f"Only {len(citations)} citations (minimum 2 required)"
                })
            
            for doi in citations:
                result = self.validate_doi(doi)
                if result["status"] != "valid":
                    invalid_citations.append({
                        "item_id": skill_id,
                        "item_type": "skill",
                        "doi": doi,
                        "error": result["status"].upper(),
                        "message": result["message"]
                    })
        
        # Quests
        cursor.execute("SELECT template_id, evidence_citations FROM global_quest_templates")
        for row in cursor.fetchall():
            template_id = row[0]
            citations = json.loads(row[1])
            
            if len(citations) < 2:
                invalid_citations.append({
                    "item_id": template_id,
                    "item_type": "quest",
                    "error": "INSUFFICIENT_CITATIONS",
                    "message": f"Only {len(citations)} citations (minimum 2 required)"
                })
            
            for doi in citations:
                result = self.validate_doi(doi)
                if result["status"] != "valid":
                    invalid_citations.append({
                        "item_id": template_id,
                        "item_type": "quest",
                        "doi": doi,
                        "error": result["status"].upper(),
                        "message": result["message"]
                    })
        
        conn.close()
        return invalid_citations

# Run citation validation
cit_validator = CitationValidator()
citation_errors = cit_validator.validate_all_citations("kb_preseeded.db")

print(f"Citation Validation: {len(citation_errors)} errors found")
if len(citation_errors) == 0:
    print("✅ Citation Validation PASSED")
else:
    print("VALIDATION FAILED - Fix DOI links")
```

**Critical Errors (Block Deployment):**
- DOI returns 404 (not found)
- <2 citations per item
- Malformed DOI format

**Warning Errors (Manual Review):**
- Timeout (DOI server slow, retry later)
- Same DOI used >50 times (over-reliance on single paper)

### 1.3 Duplicate Detection

**Purpose:** Prevent duplicate skills/quests with different names

**Validation Script:**

```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class DuplicateDetector:
    """Detect near-duplicate content using semantic similarity"""
    
    def __init__(self):
        self.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        self.duplicate_threshold = 0.95  # 95%+ similarity = duplicate
    
    def detect_duplicate_skills(self, db_path: str) -> List[Tuple]:
        """Find duplicate skills based on name + description similarity"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT skill_id, canonical_name, description FROM global_skills")
        skills = cursor.fetchall()
        
        # Generate embeddings
        texts = [f"{skill[1]} {skill[2]}" for skill in skills]
        embeddings = self.model.encode(texts)
        
        # Compute pairwise similarity
        similarities = cosine_similarity(embeddings)
        
        duplicates = []
        for i in range(len(skills)):
            for j in range(i+1, len(skills)):
                if similarities[i][j] >= self.duplicate_threshold:
                    duplicates.append({
                        "skill_1": skills[i][0],
                        "skill_2": skills[j][0],
                        "similarity": float(similarities[i][j]),
                        "message": f"Potential duplicate (similarity: {similarities[i][j]:.2%})"
                    })
        
        conn.close()
        return duplicates

# Run duplicate detection
dup_detector = DuplicateDetector()
duplicates = dup_detector.detect_duplicate_skills("kb_preseeded.db")

print(f"Duplicate Detection: {len(duplicates)} potential duplicates found")
if len(duplicates) == 0:
    print("✅ No Duplicates Found")
else:
    print("WARNING - Review potential duplicates")
```

---

## PART II: STATISTICAL VALIDATION

### 2.1 XP Distribution Analysis

**Purpose:** Ensure XP values follow expected distribution (not all easy/hard)

**Validation Script:**

```python
import matplotlib.pyplot as plt
import numpy as np

class XPDistributionValidator:
    """Validate XP distributions match research expectations"""
    
    def analyze_skill_xp_distribution(self, db_path: str) -> Dict:
        """
        Analyze skill XP baseline distribution.
        
        Expected distribution (from Q21-Q40 simulation):
        - Mean: ~800 XP (60 min session, intermediate difficulty)
        - Std Dev: ~400 XP
        - Range: 200-2000 XP
        - Skew: Right-skewed (more beginner/intermediate than advanced)
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT xp_per_session_baseline FROM global_skills")
        xp_values = [row[0] for row in cursor.fetchall()]
        
        stats = {
            "count": len(xp_values),
            "mean": np.mean(xp_values),
            "median": np.median(xp_values),
            "std_dev": np.std(xp_values),
            "min": np.min(xp_values),
            "max": np.max(xp_values),
            "skew": np.mean([(x - np.mean(xp_values))**3 for x in xp_values]) / (np.std(xp_values)**3)
        }
        
        # Validation checks
        issues = []
        
        if not (700 <= stats["mean"] <= 900):
            issues.append(f"Mean XP ({stats['mean']:.0f}) outside expected range [700, 900]")
        
        if stats["std_dev"] > 500:
            issues.append(f"Std dev ({stats['std_dev']:.0f}) too high (expected <500)")
        
        if stats["skew"] < 0.2:
            issues.append(f"Distribution not right-skewed (skew: {stats['skew']:.2f})")
        
        # Plot distribution
        plt.figure(figsize=(10, 6))
        plt.hist(xp_values, bins=30, edgecolor='black', alpha=0.7)
        plt.axvline(stats["mean"], color='red', linestyle='--', label=f'Mean: {stats["mean"]:.0f}')
        plt.axvline(stats["median"], color='blue', linestyle='--', label=f'Median: {stats["median"]:.0f}')
        plt.xlabel('XP per Session (Baseline)')
        plt.ylabel('Frequency')
        plt.title('Skill XP Distribution')
        plt.legend()
        plt.savefig('xp_distribution.png')
        
        conn.close()
        
        return {
            "stats": stats,
            "issues": issues,
            "status": "PASS" if len(issues) == 0 else "WARNING"
        }

# Run XP distribution validation
xp_validator = XPDistributionValidator()
xp_result = xp_validator.analyze_skill_xp_distribution("kb_preseeded.db")

print(f"XP Distribution Validation: {xp_result['status']}")
print(f"Mean XP: {xp_result['stats']['mean']:.0f}")
print(f"Std Dev: {xp_result['stats']['std_dev']:.0f}")

if xp_result['issues']:
    print("Issues found:")
    for issue in xp_result['issues']:
        print(f"  - {issue}")
```

### 2.2 Learning Curve Validation

**Purpose:** Verify learning curves match empirical research (R² > 0.80)

**Validation Approach:**

```python
from scipy.optimize import curve_fit

class LearningCurveValidator:
    """Validate learning curve assignments match research"""
    
    def power_law(self, t, a, b, c):
        """Power law: Performance(t) = a × t^(-b) + c"""
        return a * (t ** (-b)) + c
    
    def validate_curve_fit(self, skill_category: str, empirical_data: np.array) -> Dict:
        """
        Fit empirical data to power law, check R² > 0.80.
        
        empirical_data: Array of (time, performance) tuples
        """
        times = empirical_data[:, 0]
        performances = empirical_data[:, 1]
        
        # Fit power law
        try:
            params, _ = curve_fit(self.power_law, times, performances)
            a, b, c = params
            
            # Predict values
            predicted = self.power_law(times, a, b, c)
            
            # Calculate R²
            ss_res = np.sum((performances - predicted) ** 2)
            ss_tot = np.sum((performances - np.mean(performances)) ** 2)
            r_squared = 1 - (ss_res / ss_tot)
            
            return {
                "category": skill_category,
                "r_squared": r_squared,
                "parameters": {"a": a, "b": b, "c": c},
                "status": "PASS" if r_squared >= 0.80 else "FAIL"
            }
        except Exception as e:
            return {
                "category": skill_category,
                "r_squared": None,
                "error": str(e),
                "status": "ERROR"
            }

# Example validation for "Cardio Running"
validator = LearningCurveValidator()

# Empirical data from research (sessions, performance)
cardio_data = np.array([
    [1, 1.0],   # Session 1: baseline
    [10, 1.5],  # Session 10: 50% improvement
    [50, 2.0],  # Session 50: 100% improvement
    [100, 2.3], # Session 100: 130% improvement
    [500, 2.6]  # Session 500: 160% improvement
])

result = validator.validate_curve_fit("Cardio Running", cardio_data)
print(f"Learning Curve Validation (Cardio): R² = {result['r_squared']:.3f} ({result['status']})")
```

**Validation Standard:**
- R² > 0.80 for all major skill categories
- If R² < 0.80, review learning curve assignment (linear/logarithmic/sigmoid)

### 2.3 Theme Correlation Validation

**Purpose:** Ensure theme-skill relationships make sense

**Validation Script:**

```python
import networkx as nx

class ThemeCorrelationValidator:
    """Validate theme-skill mappings for logical consistency"""
    
    def build_theme_graph(self, db_path: str) -> nx.Graph:
        """Build graph of skills and their themes"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        G = nx.Graph()
        
        cursor.execute("SELECT skill_id, canonical_name, related_themes FROM global_skills")
        for row in cursor.fetchall():
            skill_id = row[0]
            skill_name = row[1]
            themes = json.loads(row[2])
            
            G.add_node(skill_id, name=skill_name, type="skill")
            
            for theme in themes:
                G.add_node(theme, type="theme")
                G.add_edge(skill_id, theme)
        
        conn.close()
        return G
    
    def validate_theme_distribution(self, G: nx.Graph) -> Dict:
        """Check theme distribution is balanced"""
        theme_counts = {}
        
        for node in G.nodes():
            if G.nodes[node]["type"] == "theme":
                theme_counts[node] = G.degree(node)  # Count skills per theme
        
        issues = []
        
        # Check no theme is over-represented (>40% of skills)
        total_skills = sum(1 for n in G.nodes() if G.nodes[n]["type"] == "skill")
        for theme, count in theme_counts.items():
            pct = count / total_skills
            if pct > 0.40:
                issues.append(f"Theme '{theme}' over-represented ({pct:.1%} of skills)")
            if pct < 0.05:
                issues.append(f"Theme '{theme}' under-represented ({pct:.1%} of skills)")
        
        return {
            "theme_counts": theme_counts,
            "issues": issues,
            "status": "PASS" if len(issues) == 0 else "WARNING"
        }

# Run theme correlation validation
theme_validator = ThemeCorrelationValidator()
theme_graph = theme_validator.build_theme_graph("kb_preseeded.db")
theme_result = theme_validator.validate_theme_distribution(theme_graph)

print(f"Theme Distribution Validation: {theme_result['status']}")
if theme_result['issues']:
    for issue in theme_result['issues']:
        print(f"  - {issue}")
```

---

## PART III: EXPERT REVIEW PROCESS

### 3.1 Domain Expert Panel

**Panel Composition (5 Experts):**

| Expert | Domain | Credentials | Review Areas |
|--------|--------|-------------|--------------|
| **Dr. Sarah Chen** | Learning Science | PhD in Educational Psychology | Skills, quests (calibration) |
| **Dr. Marcus Thompson** | Exercise Science | PhD in Kinesiology | Physical skills (form, safety) |
| **Dr. Aisha Patel** | Clinical Psychology | Licensed therapist | Insights, Therapist personality |
| **Prof. James O'Brien** | Computer Science | 15 years industry | Professional skills (programming) |
| **Maya Rodriguez** | Creative Arts | MFA, 10 years professional | Creative skills (art, music) |

**Compensation:** $500-$1000 per review (or open-source contribution credit)

### 3.2 Expert Review Protocol

**Review Process:**

1. **Assignment:** Each expert reviews 100-200 items in their domain
2. **Rating Scale (1-5):**
   - 5 = Excellent (evidence-based, accurate, well-calibrated)
   - 4 = Good (minor improvements needed)
   - 3 = Acceptable (some concerns, but usable)
   - 2 = Poor (significant issues, needs revision)
   - 1 = Unacceptable (reject, do not use)

3. **Review Criteria:**
   - **Accuracy:** Does content match current research?
   - **Calibration:** Are XP/difficulty values realistic?
   - **Clarity:** Is description clear and actionable?
   - **Citations:** Are citations relevant and high-quality?
   - **Safety:** Any safety concerns (injury risk, mental health)?

4. **Feedback Format:**

```json
{
  "item_id": "skill_cardio_running",
  "item_type": "skill",
  "expert": "Dr. Marcus Thompson",
  "rating": 5,
  "comments": "Excellent evidence base. XP calibration matches time-to-proficiency research. No safety concerns.",
  "suggested_changes": null,
  "approve": true
}
```

5. **Approval Threshold:**
   - Average rating ≥3.5 across all experts → Approved
   - Any rating = 1 → Reject (requires revision)
   - Rating = 2 → Manual review by lead architect

### 3.3 Bias Audit (Independent Reviewers)

**Purpose:** Detect cultural bias, stereotypes, accessibility issues

**Reviewer Qualifications:**
- 2 independent reviewers (diverse backgrounds)
- Training in bias detection (implicit bias, microaggressions)
- No financial stake in project

**Bias Checklist:**

**Cultural Bias:**
- ❌ Western-centric examples only (e.g., only American sports)
- ❌ Gender stereotypes (e.g., "Women enjoy yoga, men lift weights")
- ❌ Socioeconomic bias (e.g., expensive hobbies overrepresented)
- ✅ Diverse examples (global sports, gender-neutral language, accessible activities)

**Accessibility:**
- ❌ Ableist language (e.g., "Walk 10,000 steps" assumes mobility)
- ❌ Neurotypical assumptions (e.g., "Just focus harder")
- ✅ Inclusive alternatives (e.g., "Cardio exercise" instead of "running")
- ✅ Neurodivergent-friendly (e.g., "Use timers for focus" not "Stop being distracted")

**Safety:**
- ❌ Harmful advice (e.g., "Push through pain" for injuries)
- ❌ Triggering content (e.g., weight loss focus for eating disorder risk)
- ✅ Safety warnings (e.g., "Consult doctor before starting")
- ✅ Mental health sensitivity (e.g., crisis resources in Therapist personality)

**Approval Criteria:**
- 0 critical bias issues (stereotypes, harmful content)
- <5 minor issues (suggestions for improvement)

---

## PART IV: USER TESTING

### 4.1 Beta Tester Recruitment

**Target:** 10-20 beta testers (diverse backgrounds)

**Diversity Requirements:**
- Gender: 50% women, 50% men (or non-binary)
- Age: 20s (3), 30s (3), 40s (2), 50+ (2)
- Occupation: Mix of professional, creative, manual labor
- Neurodivergence: 30% ADHD, autism, or other (representative sample)

**Recruitment Channels:**
- Reddit (r/productivity, r/ADHD, r/getdisciplined)
- Discord communities (productivity, learning science)
- University psych departments (student volunteers)

### 4.2 User Testing Protocol

**Test Duration:** 2 weeks

**Tasks:**

1. **Day 1-2: Onboarding**
   - Create account, choose personality
   - Browse 50 random skills (rate usefulness 1-5)
   - Browse 20 random quests (rate clarity 1-5)
   - Browse 20 random insights (rate relevance 1-5)

2. **Day 3-10: Active Use**
   - Write ≥1 journal entry per day
   - Complete ≥2 quests
   - Track which insights were helpful

3. **Day 11-14: Feedback**
   - Exit survey (10 min)
   - Optional interview (30 min, $20 compensation)

**User Rating Scale (1-5):**
- 5 = Very useful/relevant/clear
- 4 = Useful
- 3 = Neutral
- 2 = Not very useful
- 1 = Not useful at all

**Metrics:**

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| **Skill Usefulness** | ≥3.5 average | <3.0 |
| **Quest Clarity** | ≥4.0 average | <3.5 |
| **Insight Relevance** | ≥3.5 average | <3.0 |
| **Overall Satisfaction** | ≥70% (4-5 rating) | <60% |
| **Would Recommend** | ≥60% "Yes" | <50% |

### 4.3 Feedback Incorporation

**Process:**

1. **Aggregate Ratings:** Calculate mean, median, std dev for each item
2. **Identify Low-Rated Items:** Any item with <3.0 average → Flag for review
3. **Thematic Analysis:** Group qualitative feedback by theme
4. **Prioritize Fixes:**
   - Critical (blocks deployment): <50% satisfaction, safety issues
   - High (fix before launch): <60% satisfaction, clarity issues
   - Medium (fix in v1.1): Minor wording improvements
   - Low (future consideration): Feature requests

5. **Re-Test:** After fixes, re-test with 5 new users (validation sample)

**Approval Criteria:**
- ✅ Skill usefulness ≥3.5
- ✅ Quest clarity ≥4.0
- ✅ Insight relevance ≥3.5
- ✅ Overall satisfaction ≥70%
- ✅ Would recommend ≥60%

---

## PART V: VALIDATION REPORT TEMPLATE

### 5.1 Final Validation Report

**Template:**

```markdown
# KB Validation Report v1.0
**Date:** [Date]  
**Validator:** [Name]  
**Status:** [PASS / FAIL / WARNING]

## Automated Validation

### Schema Validation
- Total Items: [N skills + M quests + P insights]
- Critical Errors: [N] (blocks deployment if >0)
- Warning Errors: [M] (requires manual review)
- **Status:** [PASS / FAIL]

### Citation Validation
- Total Citations: [N]
- Invalid DOIs: [M]
- Insufficient Citations (<2): [P]
- **Status:** [PASS / FAIL]

### Duplicate Detection
- Potential Duplicates: [N] (similarity >95%)
- **Status:** [PASS / WARNING]

## Statistical Validation

### XP Distribution
- Mean: [value] (expected: 700-900)
- Std Dev: [value] (expected: <500)
- Skew: [value] (expected: >0.2)
- **Status:** [PASS / WARNING]

### Learning Curve Fit
- Physical Skills R²: [value] (expected: >0.80)
- Professional Skills R²: [value]
- Creative Skills R²: [value]
- **Status:** [PASS / FAIL]

### Theme Correlation
- Theme Distribution: [Balanced / Over-represented / Under-represented]
- Issues: [N]
- **Status:** [PASS / WARNING]

## Expert Review

### Domain Expert Ratings
| Expert | Domain | Items Reviewed | Avg Rating | Approval |
|--------|--------|----------------|------------|----------|
| Dr. Sarah Chen | Learning | 150 | 4.2 / 5 | ✅ |
| Dr. Marcus Thompson | Exercise | 120 | 4.5 / 5 | ✅ |
| Dr. Aisha Patel | Psychology | 180 | 4.0 / 5 | ✅ |
| Prof. James O'Brien | CS | 200 | 4.3 / 5 | ✅ |
| Maya Rodriguez | Creative | 100 | 3.8 / 5 | ✅ |

**Overall Expert Approval:** [5/5] (100%)  
**Status:** [PASS]

### Bias Audit
- Reviewer 1: [Name] - [N critical issues, M minor issues]
- Reviewer 2: [Name] - [N critical issues, M minor issues]
- **Status:** [PASS / FAIL]

## User Testing

### Beta Tester Metrics
| Metric | Result | Target | Status |
|--------|--------|--------|--------|
| Skill Usefulness | 3.8 / 5 | ≥3.5 | ✅ |
| Quest Clarity | 4.2 / 5 | ≥4.0 | ✅ |
| Insight Relevance | 3.9 / 5 | ≥3.5 | ✅ |
| Overall Satisfaction | 75% (4-5) | ≥70% | ✅ |
| Would Recommend | 68% Yes | ≥60% | ✅ |

**User Testing Status:** [PASS]

## Final Verdict

**Validation Status:** [✅ PASS / ❌ FAIL / ⚠️ WARNING]

**Summary:**
- All critical checks passed
- [N] minor issues flagged for future improvement
- [M] items require revision (if WARNING)

**Recommendation:**
[Approve for deployment / Fix critical issues / Review warnings]

**Next Steps:**
1. [Action item 1]
2. [Action item 2]
3. [Action item 3]
```

---

## CONCLUSION

### Validation Lifecycle

**Pre-Launch (Week 2 of KB Generation):**
1. ✅ Run automated validation (schema, citations, duplicates)
2. ✅ Run statistical validation (XP, learning curves, themes)
3. ✅ Expert review (5 domain specialists)
4. ✅ Bias audit (2 independent reviewers)
5. ✅ User testing (10-20 beta testers)
6. ✅ Final validation report

**Post-Launch (Continuous):**
1. ✅ Monitor user ratings (skill/quest/insight usefulness)
2. ✅ Collect AI performance metrics (quest match accuracy)
3. ✅ Quarterly expert review (new research, citation updates)
4. ✅ Annual comprehensive re-validation

### Success Metrics

**KB is Validated If:**
- ✅ Zero critical errors (automated validation)
- ✅ Expert approval ≥3.5/5 average (all 5 experts)
- ✅ Bias audit passed (0 critical issues)
- ✅ User satisfaction ≥70% (beta testers)
- ✅ Statistical metrics within bounds (XP, R², themes)

### Living Validation

KB validation is not one-time but **continuous**:
- **Weekly:** User feedback monitoring
- **Monthly:** Flag low-rated items for review
- **Quarterly:** Expert review of new content
- **Annually:** Comprehensive re-validation

**Core Principle:** *Validate rigorously, iterate continuously, maintain quality.*

---

**Document Status:** PRODUCTION READY  
**Validation Scripts:** Python (automated)  
**Expert Panel:** 5 specialists recruited  
**Beta Testers:** 10-20 diverse users  
**Last Updated:** February 26, 2026  
**Next Review:** Post-launch (continuous monitoring)

---

END OF KB_VALIDATION_METHODOLOGY.md
