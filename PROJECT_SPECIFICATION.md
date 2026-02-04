# PROJECT SPECIFICATION: Life Sucks But You Got a Status Window Now
## Gamified Journaling Application for Neurodivergent Users

**Version:** 1.0.0  
**Last Updated:** February 4, 2026  
**Target MVP Completion:** Mid-March 2026 (~6 weeks)  
**Primary Developer:** Sebastian (RedsMod)  
**Initial Users:** 3 (Sebastian + 2 friends, all 23-25 yo, ADHD/Autism spectrum)

---

## 🎯 EXECUTIVE SUMMARY

### Core Value Proposition
**"This app turns your life into a character sheet you can level up by automatically tracking your life progress across multiple dimensions."**

### The Problem We Solve
Neurodivergent individuals (ADHD/Autism spectrum) struggle with:
- Executive dysfunction making traditional productivity tools overwhelming
- Lack of dopamine feedback from daily tasks
- All-or-nothing thinking causing habit abandonment after one missed day
- Traditional journaling feeling pointless and disconnected
- No visible sense of life progress outside of work
- Existing gamification apps being too simplistic and non-adaptive

### The Solution
A **system-based journaling app** inspired by Korean manhwa/light novels (Solo Leveling, The Gamer, etc.) that:
- Automatically converts life activities into RPG-style progression (XP, Skills, Titles, Quests)
- Uses AI to categorize journal entries and suggest personalized Missions/Quests
- Provides immediate dopamine feedback through visible character progression
- Implements forgiveness mechanics (no shame for missed days)
- Adapts to user's energy levels and neurodivergent cognitive patterns
- Creates a "status window" interface showing life stats in real-time

---

## 👥 TARGET USER PROFILE (PRIMARY)

### Demographics
- **Age:** 18-30 (initial: 23-25)
- **Neurodiversity:** ADHD/Autism spectrum
- **Life Stage:** End of studies / early career
- **Gaming Background:** Deep RPG knowledge, grand strategy games
- **Tech Comfort:** High (but coding beginner-intermediate)

### Psychographic Profile
**Critical Traits (Design Imperatives):**

1. **Neurodivergent Strategists** - Thrive on visual systems, predictable feedback, low-pressure accountability
2. **Arborescent Thinkers** - Non-linear thought patterns, need associative connection visualization
3. **Dopamine-Dysregulated** - Struggle to initiate low-reward tasks without immediate feedback
4. **Data-Obsessed Optimizers** - Want to quantify everything but struggle with fragmented tools
5. **Skill Tree Explorers** - Map personal growth like RPG skill trees with visible mastery paths
6. **Gamers Seeking Real-Life Progression** - Crave in-game mechanics (operant conditioning + dopamine hits)
7. **Mental Health Conscious** - Close experience with chronic anxiety, diagnosed depression
8. **Crisis Navigators** - Need gentle onboarding, forgiveness mechanics, emotional safety
9. **Anti-Productivity Rebels (Limited)** - Want to reward rest/balance, not just busyness
10. **Existential Achievers** - Forget achievements easily, need visual reminder to combat "false truth" thinking

### Pain Points Addressed

| Pain Point | How We Solve It |
|-----------|----------------|
| **Lack of motivation for daily tasks** | Immediate XP feedback + Quest notifications |
| **No sense of life progress** | Visible Skills/Themes leveling + Title unlocks |
| **Mental health tracking is boring** | Narrative integration + gamified status bars |
| **Traditional journaling feels pointless** | AI auto-categorization + insight generation |
| **Difficulty maintaining habits** | Forgiveness mechanics + streak recovery |
| **Existing gamification too simplistic** | Deep branching systems + adaptive challenges |
| **Overwhelm from rigid productivity systems** | Energy-adaptive quest suggestions |
| **Inability to integrate disparate data** | Unified database (text/voice/files) |
| **Lack of storytelling in gamification** | Story Arcs + character development tied to user's life |
| **Shame-based feedback loops** | Constructive debuffs + recovery mechanics |
| **Mismatched to cognitive style** | Accordion/dropdown UI (info on-demand, not permanent display) |

---

## 🏗️ SYSTEM ARCHITECTURE

### Core Game Mechanics (8 Pillars)

#### 1. **THEMES** (Major Life Categories)
**Definition:** Broad life domains that contain Skills, Titles, and M/Q

**Attributes:**
- ID (UUID)
- Name (e.g., "Physical Health", "Education", "Spirituality", "Finances")
- Description
- Sub-Themes (hierarchical)
- Level (0-∞, with paliers/milestones)
- Experience Points (XP)
- Corrosion Level (degrades if not maintained)
- Connected Themes (relationships)
- Theme Type/Classification

**Mechanics:**
- Gains XP from: Skill level-ups, M/Q completion, Item usage
- Level up unlocks: New M/Q, Skill tree parts, Titles, Bonuses to related activities
- Corrosion: If neglected, theme "rusts" (e.g., Physical Health theme corrodes if no exercise for 2 weeks)

**Examples:**
```
Theme: Physical Health
├─ Sub-Theme: Cardio Fitness
├─ Sub-Theme: Strength Training
├─ Sub-Theme: Nutrition
└─ Sub-Theme: Sleep Quality
```

---

#### 2. **SKILLS**
**Definition:** Specific competencies that level up through practice

**Attributes:**
- ID (UUID)
- Name (e.g., "Python Programming", "Cooking", "Spanish Language")
- Description
- Level (F to S rank, inspired by Korean RPG novels)
- Rank (Beginner → Amateur → Intermediate → Advanced → Expert → Master)
- Difficulty (affects XP requirements)
- Parent Theme(s)
- Parent Skill (for skill trees)
- Child Skills (branches)
- Practice Time (cumulative hours)
- Capabilities by Level (what you can do at each rank)
- Potential Abilities to Unlock

**Mechanics:**
- Gains XP from: Practice time (M/Q completion), Titles, Cross-proficiency bonuses
- Level up provides: Titles, Unlock Missions, Skill Tree progression, Coins
- **Skill Trees:** Nested (AI→LLM→Prompting) AND Parallel (Prompting||RAG||Fine-tuning)

**Tree Structure Example:**
```
Education Skill
├─ Programming (Nested)
│   ├─ Python
│   │   ├─ Data Analysis (Parallel)
│   │   ├─ Web Development (Parallel)
│   │   └─ ML/AI (Parallel)
│   │       ├─ LLM Usage (Nested)
│   │       │   └─ Prompt Engineering
│   │       └─ Model Training (Nested)
│   └─ JavaScript
└─ Languages (Parallel to Programming)
    ├─ Spanish
    └─ French
```

**Rank Thresholds (Example):**
- Beginner: 0-100 XP
- Amateur: 100-500 XP
- Intermediate: 500-2000 XP
- Advanced: 2000-10000 XP
- Expert: 10000-50000 XP
- Master: 50000+ XP

---

#### 3. **TITLES** (Badges/Achievements)
**Definition:** Persistent or temporary modifiers that recognize achievements and shape character identity

**Attributes:**
- ID (UUID)
- Name (e.g., "Early Riser", "Social Butterfly", "Asocial", "Burnout Survivor")
- Description (personalized explanation for THIS user)
- Effect/Modifier (passive buffs/debuffs)
- Class (F to S rank)
- Categories (tags)
- Unlock Conditions
- Is Active (can be equipped/unequipped)
- Acquisition Date
- Expiration Date (if temporary)

**Mechanics:**
- **All Player Weights Are Contained in Titles** - Critical design decision
- Titles can be positive ("Healthy Eater" +10% Physical Health XP) or negative ("Asocial" -20% social quest difficulty but +50% reward when completed)
- Used to combat "false truth" thinking (e.g., user believes they never socialize → "Social Butterfly" title appears after 3 outings)
- Some titles are hidden/hinted (unlock conditions teased but not fully revealed)

**Examples:**
| Title | Effect | Unlock Condition |
|-------|--------|------------------|
| **Night Owl** | -10% morning task difficulty, +15% late-night productivity | 10 journal entries after midnight |
| **Streak Keeper** | +5% XP on all activities | 7-day consecutive journaling streak |
| **Asocial** | Social quests give +50% reward, but appear less frequently | <3 social interactions in 2 weeks |
| **Burnout Survivor** | Recovery quests give +200% XP | Complete "Rest & Recovery" story arc |

---

#### 4. **MISSIONS & QUESTS** (M/Q)
**Definition:** Tasks ranging from daily repeatable actions to multi-stage story arcs

**Quest vs Mission Philosophy:**
- **Quests:** Free will, autonomy, optional
- **Missions:** Deterministic, hand-held, structured

**Hierarchy (Inspired by RPG structure):**
```
Story Arc (e.g., "Become a Health-Conscious Person")
└─ Mission (Multi-stage, e.g., "Establish Exercise Routine")
    ├─ Sub-Mission (e.g., "Complete 30 Daily Gym Quests")
    ├─ Encounters (e.g., "Football session with Alex")
    ├─ Side Quests (e.g., "Run a half-marathon")
    ├─ Dynamic Quests (Event-induced, e.g., "Survival Trials")
    ├─ Repeatable Quests (e.g., "Do 20 pull-ups")
    ├─ Branching Quests (Choice-based outcomes)
    ├─ Milestones (e.g., "Full Flower Challenge")
    └─ Challenges (Time-limited, e.g., "7-day meditation streak")
```

**Attributes:**
- ID (UUID)
- Name
- Description (personalized context)
- Type (Daily, Timed, Periodic, Non-Timed)
- Structure (Single action, Multi-action, Multi-Part)
- Generation Source (Programmed, Event-triggered, Spontaneous, AI-suggested)
- Parent M/Q (for hierarchy)
- Child M/Q
- Completion Conditions (Yes/No, Accumulation value, Quality threshold)
- Reward (XP to Skill, XP to Theme, Coins, Items, Titles)
- Difficulty
- Deadline (optional)
- Status (Not Started, In Progress, Completed, Failed, Cancelled)

**Completion Logic:**
1. User logs activity (journal entry, manual check, or voice)
2. AI categorizes → matches to active M/Q
3. Updates completion value
4. Checks if 100% → Validates mission → Distributes rewards

**Element Reusability (Cost Optimization):**
- When M/Q is created, store in **Global Element Bank**
- Future M/Q checks bank FIRST before generating new
- Reuse with contextual personalization (e.g., "50 pushups quest" reused but text re-contextualized for current Story Arc)
- Prevents AI over-generation, maintains consistency across users

---

#### 5. **ITEMS** (Inventory System)
**Definition:** Consumables and possessions that provide buffs/debuffs

**Categories:**
- **Food/Drink** (Good: salad, water | Bad: junk food, energy drinks)
- **Brainrot Activities** (Bad: Excessive scrolling, binge-watching)
- **Educative Activities** (Books, courses, podcasts)
- **Drugs** (Caffeine, medication, etc. - tracked, not judged)
- **Activities** (Breaks, vacations, hobbies)
- **Gadgets** (Purchases tracked for spending patterns)
- **Reports/Diplomas** (Achievements with permanent buffs)

**Attributes:**
- ID (UUID)
- Name
- Description
- Effect (Buff/Debuff to XP gain, Status values)
- Market Cost (personalized based on player weights/titles)
- Price (in HP, MP, or Coins)
- Categories
- Uses (consumable count or unlimited)
- Conditions (Locked/Restricted based on level)
- Karma (Good/Bad/Neutral)

**Mechanics:**
- **Usage:** Immediate buffs/debuffs (e.g., "Coffee" = +15% focus for 4 hours, -10 HP)
- **Possession (Inventory):** Passive effects (e.g., "Guitar in inventory" = +5% Music Skill XP)
- **Selling:** Items can be sold for Coins (e.g., "Diploma" = +500 Coins + permanent Education XP boost)

---

#### 6. **STATUS BARS** (HP, Mental Health, etc.)
**Definition:** Visual representation of current state

**Core Status Attributes:**
- **HP (Hit Points):** Physical energy/health
- **MP (Mana Points):** Mental energy/focus capacity
- **Mental Health:** Mood/anxiety/depression level
- **Physical Health:** Fitness/nutrition/sleep quality
- **Relationship:** Social connection quality
- **Socialization:** Recent social activity level

**Mechanics:**
- Updated by: Journal entries (AI sentiment analysis), M/Q completion, Item usage
- Displayed as: Progress bars with thresholds (Green/Yellow/Orange/Red zones)
- Affects: Quest difficulty, available actions, Title effects

---

#### 7. **COINS** (Currency)
**Definition:** In-game currency for unlocking and skipping

**Earn Coins From:**
- M/Q completion
- Selling Items
- Skill Level Up
- New/Upgrade Title
- Theme Level Up
- Micro-Transactions (real-world money set aside for self-reward)
- Bonus Items (educational events, productive purchases)

**Spend Coins On:**
- Buy Items
- Skip Mission/Quest (cost increases with overuse to prevent abuse)
- Unlock M/Q
- Unlock Skill Tree branches
- Gain/Sustain Titles (some titles require "maintenance fee")

**Design Intent:** Coins bridge real-world decisions (spending money) with in-game progression

---

#### 8. **SPECIAL MECHANICS**

**Corrosion Level:**
- **Concept:** Themes/Skills "rust" if not used
- **Status Progression:** New → Fresh → Old → Patterned → Unrecovered
- **Effects:** Increased difficulty, slower XP gain, negative Titles
- **Recovery:** Completing related M/Q restores freshness

**Personal Player Weights:**
- **All weights stored in Titles**
- Examples: "Early Riser" title makes morning quests easier, "Night Owl" makes them harder
- Adaptive to user behavior (if user consistently exercises at 8pm, AI suggests quests at that time)

---

## 🗄️ DATABASE SCHEMA OVERVIEW

### Entity Relationship Summary

```
Users
├─ Has many → Themes
├─ Has many → Skills
├─ Has many → Titles (UserTitles join table)
├─ Has many → Missions/Quests (UserMQ join table)
├─ Has many → Items (UserInventory join table)
├─ Has many → JournalEntries
└─ Has one → UserStats (HP, MP, etc.)

Themes
├─ Belongs to → User
├─ Has many → Skills
├─ Has many → Missions/Quests
└─ Has many → Titles

Skills
├─ Belongs to → User
├─ Belongs to → Theme
├─ Has one → Parent Skill (self-referential)
├─ Has many → Child Skills
└─ Unlocks → Missions/Quests

Titles
├─ Stored in → GlobalTitleBank (shared across users)
├─ Belongs to many → Users (via UserTitles)
└─ Has many → Effects (JSON or separate table)

Missions/Quests
├─ Stored in → GlobalMQBank (reusable templates)
├─ Belongs to many → Users (via UserMQ with personalization)
├─ Belongs to → Theme
├─ Requires → Skill (optional)
├─ Has one → Parent M/Q
├─ Has many → Child M/Q
└─ Rewards → XP, Coins, Items, Titles

Items
├─ Stored in → GlobalItemBank
├─ Belongs to many → Users (via UserInventory)
└─ Has → Effects (buff/debuff logic)

JournalEntries
├─ Belongs to → User
├─ Categorized by → AI (linked to Themes/Skills)
├─ Triggers → M/Q progress
└─ Updates → UserStats

UserStats
├─ Belongs to → User
└─ Updated by → JournalEntries, M/Q completion, Items
```

### Critical Design Decisions

1. **Hybrid Database Approach:**
   - **SQLite** for local development and single-user MVP
   - **PostgreSQL** for multi-user cloud deployment
   - Schema MUST be compatible with both

2. **Element Reusability:**
   - Global banks for Titles, M/Q, Items (de-duplicated)
   - User-specific instances reference global elements
   - Personalization stored in join tables (not in element itself)

3. **JSON Fields for Flexibility:**
   - `effects` column for Titles/Items (allows dynamic buff/debuff logic)
   - `metadata` column for extensibility without schema migration

---

## 🤖 AI INTEGRATION STRATEGY

### AI Components

#### 1. **Journal Entry Categorization**
**Model:** Llama 3.2 (via Ollama, local)  
**Task:** Classify journal text into Themes, Skills, M/Q progress  
**Input:** Raw journal entry text  
**Output:** JSON with categories, keywords, sentiment, suggested M/Q

**Prompt Template:**
```python
CATEGORIZATION_PROMPT = """
You are analyzing a journal entry for a gamified life-tracking app.

User Profile:
{user_titles}
{active_themes}
{active_skills}

Journal Entry:
"{entry_text}"

Categorize this entry:
1. Which Themes does this relate to? (Physical Health, Education, etc.)
2. Which Skills were practiced? (estimate practice time in minutes)
3. Does this complete any active Missions/Quests? (check against: {active_mq})
4. Sentiment: Positive/Neutral/Negative (for Mental Health status update)
5. Suggest 1-3 new Quests based on this entry

Return JSON:
{{
  "themes": ["theme_id1", "theme_id2"],
  "skills": [
    {{"skill_id": "uuid", "practice_minutes": 30}},
  ],
  "completed_mq": ["mq_id1"],
  "sentiment": "positive",
  "suggested_quests": [
    {{"name": "...", "description": "...", "theme_id": "..."}}
  ]
}}
"""
```

#### 2. **Mission/Quest Generation**
**Model:** Llama 3.2 or Mistral 7B  
**Task:** Generate personalized M/Q based on user activity patterns  
**Check Global Bank FIRST** before generating new

**Prompt Template:**
```python
MQ_GENERATION_PROMPT = """
Generate a {mq_type} Quest for user in {theme_name} theme.

User Context:
- Current Level in {theme_name}: {theme_level}
- Active Titles: {titles}
- Recent Skills Practiced: {recent_skills}
- Energy Level (last 7 days): {energy_pattern}

Requirements:
- Difficulty: Match user's {theme_name} level
- Type: {quest_type} (Daily/Timed/Repeatable/etc.)
- Must align with neurodivergent-friendly design (low pressure, clear objectives)

Return JSON:
{{
  "name": "Quest name",
  "description": "Personalized description",
  "type": "daily",
  "completion_condition": {{"type": "yes_no"}},
  "reward_xp": 50,
  "reward_coins": 10,
  "difficulty": "medium"
}}
"""
```

#### 3. **Title Award Logic**
**Model:** Rule-based + AI explanation generator  
**Task:** Detect unlock conditions → Generate personalized award text

**Example Flow:**
```python
# Rule: User completes 7 consecutive daily journal entries
if user.journal_streak >= 7:
    title = get_or_create_title("Consistent Chronicler")
    personalized_msg = ai_generate_title_award_text(
        title_name="Consistent Chronicler",
        user_context=user.recent_achievements,
        unlock_reason="7-day journaling streak"
    )
    # Output: "Sebastian, your dedication to daily reflection has earned you
    # the 'Consistent Chronicler' title. Your 7-day streak shows commitment
    # to self-awareness. +10% XP on all Education-related quests."
```

#### 4. **Voice Input Processing**
**Model:** Faster-Whisper (local, optimized for speed)  
**Task:** Speech-to-text for journal entries  
**Post-processing:** Run through categorization AI

**Pipeline:**
```
Voice Recording → Faster-Whisper (STT) → Raw Text →
Llama 3.2 (Categorization) → Database Update → XP Distribution
```

### AI Cost Optimization

**Free/Local-Only Strategy:**
- **LLM:** Llama 3.2 or Mistral 7B via Ollama (runs on user's machine)
- **Embeddings:** all-MiniLM-L6-v2 (for semantic search in journal history)
- **Speech-to-Text:** Faster-Whisper (local inference)
- **No Cloud API Calls** (except optional future premium features)

**Element Reusability = Reduced AI Calls:**
- Generate M/Q once → Store in GlobalMQBank → Reuse with light personalization
- Example: "50 pushups quest" generated once, reused 100 times with contextual flavor text

**Estimated Compute:**
- Llama 3.2 inference: ~1-2 seconds per journal entry on mid-tier laptop
- Faster-Whisper: ~Real-time (1x) on CPU, faster on GPU
- Daily usage: ~5-10 AI calls (sustainable on local hardware)

---

## 🎨 FRONTEND DESIGN PRINCIPLES

### Neurodivergent-First UI/UX

**Core Principles:**
1. **Information on Demand, Not Permanent Display**
   - Use accordion/dropdown/collapsible sections
   - Default view: Clean dashboard with core stats
   - Detailed view: Expand for deep-dive into any element

2. **Visual Progress Representation**
   - XP bars with threshold markers
   - Skill trees with locked/unlocked visual distinction
   - "Status Window" inspired by manhwa/RPG interfaces

3. **Immediate Feedback**
   - Every action shows instant XP/Coin gain animation
   - Quest completion = celebratory notification
   - No delayed gratification (ADHD-optimized)

4. **Forgiveness Mechanics Visual Design**
   - Missed day ≠ Red X, instead "Recovery Quest Available"
   - Streak broken = "Streak Revive Token" offered (costs Coins)

5. **Adaptive Difficulty Indicators**
   - Green = Easy (low energy requirement)
   - Yellow = Medium
   - Orange = Challenging
   - Red = High difficulty (save for high-energy days)

### MVP UI Scope

**Phase 1 (MVP - 6 weeks):**
- **Terminal/CLI Interface** for data input (fastest to build)
- **Simple Web Dashboard** (read-only) for viewing:
  - Character sheet (Themes, Skills, Titles)
  - Quest list (active M/Q)
  - Recent journal entries
  - XP progress bars

**Phase 2 (Post-MVP):**
- **Progressive Web App (PWA)** with full interactivity
- **"Status Window" Interface** (manhwa-inspired design)
- **Mobile-optimized** responsive design

### Interface Structure (Target State)

```
┌─────────────────────────────────────────┐
│  STATUS WINDOW - Sebastian's Life v2.3 │
├─────────────────────────────────────────┤
│ HP: ████████░░ 80/100                  │
│ MP: ██████░░░░ 60/100                  │
│ Mental Health: ████████░░ 8/10         │
├─────────────────────────────────────────┤
│ ACTIVE THEMES                           │
│ ▼ Physical Health (Lv 12) ████░ 75%   │
│   └─ Skills: Cardio (Lv 8), Strength..│
│ ▼ Education (Lv 15) ███████░ 88%      │
│   └─ Skills: Python (Lv 10), ML...    │
├─────────────────────────────────────────┤
│ ACTIVE QUESTS (3)                       │
│ ☐ Daily: 30-min Coding Session [●○○]  │
│ ☐ Weekly: Gym 3x this week [●●○]      │
│ ✓ Side: Finish ML Course Module 3     │
├─────────────────────────────────────────┤
│ TITLES (5 Equipped)                     │
│ ★ Consistent Chronicler (+10% Edu XP) │
│ ★ Night Owl (-10% morning difficulty) │
├─────────────────────────────────────────┤
│ [📝 New Entry] [🎯 Quests] [💼 Inventory]│
└─────────────────────────────────────────┘
```

---

## 🚀 MVP FEATURE SCOPE (6-WEEK TIMELINE)

### MUST HAVE (Core Loop)

1. **Journal Entry System**
   - Text input (CLI + web form)
   - Voice upload (record on phone → upload file → transcribe)
   - Manual categorization (select Theme/Skill from dropdown)

2. **AI Categorization**
   - Llama 3.2 integration via Ollama
   - Auto-detect Themes, Skills, M/Q progress from entry
   - Sentiment analysis for Mental Health status

3. **XP & Leveling**
   - XP distribution to Themes/Skills
   - Level-up calculations with thresholds
   - Visual progress bars

4. **Skills System**
   - Create Skills (manual for MVP)
   - Track practice time
   - Level up Skills → Award Titles

5. **Titles System**
   - Award Titles based on achievements
   - Store effects (JSON in database)
   - Display active Titles on character sheet

6. **Missions/Quests**
   - Manual M/Q creation (admin interface)
   - Track completion status
   - Reward distribution (XP, Coins)
   - Support for Daily, Repeatable, Timed quests

7. **Basic Web Dashboard**
   - View character sheet (Themes, Skills, Titles)
   - View active M/Q list
   - View recent journal entries
   - Simple XP progress visualization

### NICE TO HAVE (MVP Stretch Goals)

8. **Themes System**
   - Create Themes (manual)
   - Theme leveling
   - Theme corrosion (basic version)

9. **Coins/Currency**
   - Earn Coins from M/Q
   - Spend Coins to skip quests
   - Display Coin balance

10. **Voice Input**
    - Faster-Whisper integration
    - Upload .mp3/.wav → Auto-transcribe → Categorize

11. **AI Insights**
    - Weekly summary of progress
    - Suggested new Quests based on patterns

12. **Simple RPG-Style Interface**
    - Status bars with HP/MP
    - Quest list with checkboxes
    - Title badges

### LATER (Post-MVP)

- Items/Inventory system
- Status bars (HP, Mental Health calculated)
- Data visualization (graphs, trends)
- Multi-language support
- Story Arcs (multi-stage missions)
- Social features (share Titles with friends)
- Advanced Skill Trees (branching, prerequisites)
- Corrosion system (full implementation)
- Mobile app (native or PWA optimization)

---

## 🛠️ TECHNOLOGY STACK (FINALIZED)

### Backend
- **Language:** Python 3.10+
- **Framework:** **FastAPI** (Recommended over Flask/Django)
  - ✅ Async support (future-proof for AI calls)
  - ✅ Auto-generated API docs (Swagger UI)
  - ✅ Pydantic validation (type safety)
  - ✅ AI-assisted coding friendly (clear patterns)
- **ORM:** SQLAlchemy 2.0 (works with SQLite & PostgreSQL)
- **Migration:** Alembic (database version control)

### Database
- **Development:** SQLite (local, fast, zero config)
- **Production:** PostgreSQL (cloud, multi-user ready)
- **Schema:** Designed to work with both (no DB-specific features in MVP)

### AI/NLP
- **LLM:** Llama 3.2 via Ollama (local inference)
- **Embeddings:** all-MiniLM-L6-v2 (sentence-transformers)
- **Speech-to-Text:** Faster-Whisper (local, optimized)
- **LLM Framework:** LangChain (optional, for complex prompts)

### Frontend
- **MVP (Week 1-6):** 
  - Simple HTML/CSS/JS (served by FastAPI)
  - Jinja2 templates (dynamic content)
  - No framework = Faster development for beginner
- **Post-MVP:**
  - React or Vue.js (for PWA)
  - Tailwind CSS (utility-first styling)

### Deployment & Hosting
- **Development:** Local (laptop + Raspberry Pi for AI)
- **Production (Future):**
  - Backend: Railway.app or Render.com (~$5-10/mo)
  - Database: Supabase (PostgreSQL, free tier) or managed instance
  - Static Files: Cloudflare Pages (free)
  - AI Models: Run on Raspberry Pi (accessible via VPN or Cloudflare Tunnel)

### Development Tools
- **IDE:** VS Code with:
  - GitHub Copilot (AI pair programming)
  - Claude Code extension (AI-assisted coding)
- **Version Control:** Git + GitHub
- **Testing:** pytest (Python), Playwright (future E2E tests)
- **Linting:** ruff (fast Python linter)

---

## 📁 PROJECT STRUCTURE (RECOMMENDED)

```
journal_bot/
├── .gitignore
├── README.md
├── PROJECT_SPECIFICATION.md          # THIS FILE (Single source of truth)
├── DEVELOPMENT_GUIDE.md              # Step-by-step implementation guide
├── requirements.txt                   # Python dependencies
├── pyproject.toml                     # Modern Python project config
├── .env.example                       # Environment variables template
│
├── app/                               # Main application
│   ├── __init__.py
│   ├── main.py                        # FastAPI app entry point
│   ├── config.py                      # Configuration (DB, AI models, etc.)
│   │
│   ├── models/                        # SQLAlchemy models (database tables)
│   │   ├── __init__.py
│   │   ├── user.py                    # User model
│   │   ├── theme.py                   # Theme model
│   │   ├── skill.py                   # Skill model
│   │   ├── title.py                   # Title model
│   │   ├── mission_quest.py           # M/Q model
│   │   ├── item.py                    # Item model
│   │   ├── journal_entry.py           # Journal entry model
│   │   └── user_stats.py              # User stats (HP, MP, etc.)
│   │
│   ├── schemas/                       # Pydantic schemas (API validation)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── theme.py
│   │   ├── skill.py
│   │   └── journal.py
│   │
│   ├── crud/                          # Database operations (Create, Read, Update, Delete)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── theme.py
│   │   ├── skill.py
│   │   ├── title.py
│   │   ├── mission_quest.py
│   │   └── journal.py
│   │
│   ├── api/                           # API endpoints (routes)
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── journal.py             # POST /journal/entry, GET /journal/entries
│   │   │   ├── character.py           # GET /character (themes, skills, titles)
│   │   │   ├── quests.py              # GET /quests, POST /quests/complete
│   │   │   └── admin.py               # Admin endpoints (create M/Q, Titles, etc.)
│   │
│   ├── ai/                            # AI integration modules
│   │   ├── __init__.py
│   │   ├── ollama_client.py           # Ollama API wrapper
│   │   ├── categorizer.py             # Journal entry categorization
│   │   ├── quest_generator.py         # M/Q generation
│   │   ├── title_generator.py         # Title award text generation
│   │   ├── whisper_client.py          # Faster-Whisper integration
│   │   └── prompts.py                 # Prompt templates
│   │
│   ├── core/                          # Core game logic
│   │   ├── __init__.py
│   │   ├── xp_calculator.py           # XP distribution, level-up logic
│   │   ├── title_awarder.py           # Title unlock detection
│   │   ├── quest_matcher.py           # Match journal entries to M/Q
│   │   ├── corrosion.py               # Theme/Skill corrosion logic
│   │   └── rewards.py                 # Reward distribution (Coins, Items, etc.)
│   │
│   ├── utils/                         # Utility functions
│   │   ├── __init__.py
│   │   ├── database.py                # DB session management
│   │   ├── security.py                # Authentication (future)
│   │   └── helpers.py                 # Misc helper functions
│   │
│   └── templates/                     # HTML templates (Jinja2)
│       ├── base.html
│       ├── dashboard.html             # Character sheet + quest list
│       ├── journal.html               # Journal entry form
│       └── quest_detail.html
│
├── alembic/                           # Database migrations
│   ├── versions/
│   └── env.py
│
├── data/                              # Local data storage
│   ├── database.db                    # SQLite database (gitignored)
│   ├── voice_uploads/                 # Uploaded voice files
│   └── backups/                       # Database backups
│
├── scripts/                           # Utility scripts
│   ├── initialize_db.py               # Create tables, seed data
│   ├── seed_global_elements.py        # Populate GlobalTitleBank, etc.
│   └── backup_db.py                   # Backup script
│
├── tests/                             # Unit and integration tests
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_api.py
│   ├── test_ai.py
│   └── test_core.py
│
└── docs/                              # Documentation
    ├── API.md                         # API endpoint documentation
    ├── DATABASE_SCHEMA.md             # ERD and table details
    ├── AI_INTEGRATION.md              # AI model usage guide
    └── DEPLOYMENT.md                  # Deployment instructions
```

---

## 🎯 SUCCESS CRITERIA

### MVP Success (Personal Use - 30 Days)
- ✅ I use it daily for 30 consecutive days
- ✅ I can see clear XP/level progress visualization
- ✅ It motivates me to complete at least 3 tasks/day (that I wouldn't otherwise)
- ✅ AI categorization accuracy >70% (manual review sample)
- ✅ No data loss (automatic backups working)

### Beta Success (Friends - 60 Days)
- ✅ Both friends use it for 14+ days
- ✅ Positive qualitative feedback (enjoyment, motivation boost)
- ✅ Large quantitative data collected (100+ journal entries per user)
- ✅ At least 5 user-requested features identified
- ✅ No critical bugs reported

### Launch Success (Future - 6+ Months)
- ✅ Running cost ≤ Revenue (break-even or profit)
- ✅ 10+ active users (if opened to wider audience)
- ✅ User retention >50% after 30 days
- ✅ Net Promoter Score (NPS) >7/10

---

## ⚠️ CRITICAL DESIGN CONSTRAINTS

### Non-Negotiables
1. **Neurodivergent-First:** Every design decision must pass the "Would this work for someone with ADHD/Autism?" test
2. **Forgiveness Over Punishment:** Missed days = recovery opportunity, not shame spiral
3. **Element Reusability:** ALWAYS check Global Element Bank before AI generation
4. **Local AI Only (MVP):** No cloud AI API calls (cost = $0 for AI)
5. **Data Permanence:** User expects ALL data to be stored forever (no auto-deletion)
6. **Info on Demand:** UI must be collapsible/expandable (not overwhelming by default)

### Trade-offs Accepted
- **MVP = CLI + Simple Web:** Polish comes later, function first
- **Manual M/Q Creation (MVP):** AI generation comes in Phase 2
- **Single-User Database (MVP):** Multi-user architecture comes later
- **No Mobile App (MVP):** PWA comes in Phase 2

---

## 📚 REFERENCES & INSPIRATION

### Manhwa/Light Novel Systems
- **Solo Leveling** (Quest notifications, level-up celebrations)
- **The Gamer** (Stats, Skills, Quests directly from real life)
- **Pick Me Up Infinite Gacha** (Element reusability concept)
- **Greatest Estate Developer** (Construction missions as life quests)
- **Transcension Academy** (Skill tree complexity)
- **War God System I'm Counting On You** (System personality, adaptive suggestions)

### Productivity/Tracking Apps (What NOT to Do)
- **Habitica:** Too simplistic, childish, non-adaptive
- **Todoist:** Rigid, no gamification depth
- **Notion:** Overwhelming, manual effort required
- **Daylio:** Clinical, boring, no narrative

### Neurodivergent Design Resources
- ADHD-friendly UI: Reduced cognitive load, immediate feedback
- Autism-friendly UI: Predictable navigation, detailed information access

---

## 🔐 DATA PRIVACY & ETHICS

### MVP Stance (3-User Private Beta)
- **Zero GDPR Compliance Required** (private use, all users consent)
- **No Encryption** (trusted users only)
- **Full Database Access** for developer (Sebastian)
- **Inter-User Privacy:** Users can hide/show specific Titles, M/Q, etc. from friends

### Future Public Launch Requirements
- **GDPR Compliance:** Right to access, delete, export data
- **Encryption:** E2E for sensitive data (journal entries)
- **Privacy Policy:** Transparent data usage
- **Consent Management:** Opt-in for AI analysis

---

## 🚨 RISK REGISTER (TOP 5)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Scope Creep** (Too many features, miss deadline) | HIGH | HIGH | Ruthless MVP scoping, defer "Nice to Have" |
| **AI Categorization Accuracy <70%** | MEDIUM | MEDIUM | Manual fallback, continuous prompt refinement |
| **User Abandonment After 7 Days** (Novelty wears off) | MEDIUM | HIGH | Forgiveness mechanics, celebration animations, friend accountability |
| **Database Schema Redesign Mid-MVP** | MEDIUM | MEDIUM | Upfront ERD design, Alembic migrations, test with sample data early |
| **Local AI Too Slow** (>5 sec per entry) | LOW | MEDIUM | Optimize prompts, use smaller models, async processing |

---

## 📞 SUPPORT & CONTACT

**Developer:** Sebastian (RedsMod)  
**Repo:** https://github.com/RedsMod721/journal_bot  
**Initial Users:** Sebastian + 2 friends (private beta)

---

**END OF PROJECT SPECIFICATION v1.0.0**

_This document is the single source of truth for all development decisions. When in doubt, refer here. Update version number when major changes are made._
