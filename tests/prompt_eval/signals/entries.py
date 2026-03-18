"""Eval corpus for the signals step (step 07) skill detection.

This file is the primary human-editable source of truth for skill detection tests.

How to read entries
-------------------
expected_skills   : canonical_names (or user roster names) that MUST appear in output.
                    An empty list means this is a pure negative / discovery test.
excluded_skills   : canonical_names that must NOT appear in any run.
acceptable_related: ok if detected but not required (partial credit, no penalty).
notes             : free-text reasoning for reviewers.

How to add entries
------------------
1. Copy an existing EvalEntry block.
2. Fill in a unique id (slug style, e.g. "phys_04_cycling").
3. Set activity_count to match the number of distinct activities in the text.
4. Adjust expected / excluded / acceptable_related.
5. Run the eval runner to verify behaviour.

Corpus distribution targets
---------------------------
Single-activity  (activity_count=1):  ~50% of corpus  (currently 14 entries)
Two-activity     (activity_count=2):  ~30% of corpus  (currently  8 entries)
Three-activity   (activity_count=3):  ~20% of corpus  (currently  6 entries)
Total: 28 entries
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalEntry:
    id: str
    """Unique slug identifier, e.g. 'phys_01_run'. Used in CLI filtering."""

    description: str
    """One-line human label shown in reports."""

    content: str
    """The journal entry text passed verbatim to signals.run()."""

    activity_count: int
    """Number of distinct activities in the entry (1, 2, or 3)."""

    l1_category: str
    """Primary L1 category: Physical / Mental / Professional / Social / Creative / Adventure."""

    l2_subcategory: str
    """Primary L2 subcategory, e.g. 'Cardio Endurance', 'Mindfulness', 'Programming'."""

    expected_skills: list[str]
    """Skill names that MUST appear in output (roster name or canonical_name from KB).
    An empty list marks a pure negative/discovery test — only fp_count is evaluated."""

    excluded_skills: list[str]
    """Skill canonical_names that must NOT appear in any run. Failures = false positives."""

    acceptable_related: list[str] = field(default_factory=list)
    """Skills that may legitimately appear but are not required (partial credit)."""

    notes: str = ""
    """Reasoning note — explains why expected/excluded are set the way they are."""


# ---------------------------------------------------------------------------
# Eval roster — seeded for the test user in eval_runner.py
# These 12 skills cover all 6 L1 categories.
# ---------------------------------------------------------------------------

EVAL_ROSTER: list[dict[str, str]] = [
    {"name": "Physical Health",    "l1": "Physical",      "l2": "Foundations"},
    {"name": "Cardio Endurance",   "l1": "Physical",      "l2": "Cardio Endurance"},
    {"name": "Mental Wellbeing",   "l1": "Mental",        "l2": "Emotional Regulation"},
    {"name": "Meditation",         "l1": "Mental",        "l2": "Mindfulness"},
    {"name": "Programming",        "l1": "Professional",  "l2": "Programming"},
    {"name": "Project Management", "l1": "Professional",  "l2": "Project Management"},
    {"name": "Communication",      "l1": "Social",        "l2": "Communication"},
    {"name": "Leadership",         "l1": "Professional",  "l2": "Leadership"},
    {"name": "Creative Writing",   "l1": "Creative",      "l2": "Writing"},
    {"name": "Music",              "l1": "Creative",      "l2": "Music"},
    {"name": "Adventure",          "l1": "Adventure",     "l2": "Foundations"},
    {"name": "Outdoor Skills",     "l1": "Adventure",     "l2": "Outdoor Skills"},
]

# ---------------------------------------------------------------------------
# SINGLE-ACTIVITY ENTRIES  (14 entries — 50% of corpus)
# ---------------------------------------------------------------------------

SINGLE_ACTIVITY: list[EvalEntry] = [
    # ── Physical / Positive ─────────────────────────────────────────────────
    EvalEntry(
        id="phys_01_run",
        description="5k run — should detect Cardio Endurance",
        content=(
            "Went for a 5k run this morning along the river path. "
            "My pace was consistent at around 5:45/km and I pushed hard on the last 500m. "
            "Felt strong and energised afterward."
        ),
        activity_count=1,
        l1_category="Physical",
        l2_subcategory="Cardio Endurance",
        expected_skills=["Cardio Endurance"],
        excluded_skills=["Meditation", "Mental Wellbeing", "Restorative Leisure"],
        acceptable_related=["Aerobic Conditioning", "Running", "Physical Health"],
    ),
    EvalEntry(
        id="phys_02_lift",
        description="Gym leg day — should detect Physical Health / Strength Training",
        content=(
            "Hit the gym today, focused on lower body. "
            "Three sets of barbell squats at 80kg, then Romanian deadlifts and leg press. "
            "My form held up well on the squats."
        ),
        activity_count=1,
        l1_category="Physical",
        l2_subcategory="Strength Training",
        expected_skills=["Physical Health"],
        excluded_skills=["Meditation", "Cardio Endurance", "Mental Wellbeing"],
        acceptable_related=["Strength Training", "Resistance Training"],
    ),
    EvalEntry(
        id="phys_03_swim",
        description="40-lap swim — should detect Cardio Endurance",
        content=(
            "Swam 40 laps at the pool, mixing freestyle and backstroke. "
            "Kept a moderate pace throughout. Exhausted but felt great after."
        ),
        activity_count=1,
        l1_category="Physical",
        l2_subcategory="Cardio Endurance",
        expected_skills=["Cardio Endurance"],
        excluded_skills=["Meditation", "Mental Wellbeing"],
        acceptable_related=["Aerobic Conditioning", "Swimming", "Physical Health"],
    ),
    # ── Physical / Negative (false-positive guard tests) ────────────────────
    EvalEntry(
        id="phys_neg_01",
        description="4h coding — must NOT trigger any physical skills",
        content=(
            "Spent 4 hours coding on the backend today. "
            "Built out the authentication service and fixed a tricky session bug. "
            "Felt productive."
        ),
        activity_count=1,
        l1_category="Professional",
        l2_subcategory="Programming",
        expected_skills=["Programming"],
        excluded_skills=["Physical Health", "Cardio Endurance", "Meditation", "Restorative Leisure"],
        notes="4h coding MUST NOT trigger physical skills — duration alone is not exercise.",
    ),
    EvalEntry(
        id="phys_neg_02",
        description="4h socialising — must NOT trigger physical skills",
        content=(
            "Had lunch with the whole team today, we were chatting and laughing for about 4 hours. "
            "Really enjoyed the connection and energy."
        ),
        activity_count=1,
        l1_category="Social",
        l2_subcategory="Conversation",
        expected_skills=["Communication"],
        excluded_skills=["Physical Health", "Cardio Endurance", "Meditation"],
        notes="4h socialising MUST NOT trigger physical skills regardless of duration.",
    ),
    EvalEntry(
        id="phys_neg_03",
        description="6h philosophy study — no physical, no meditation",
        content=(
            "Studied philosophy of mind for 6 hours today, working through "
            "Chalmers' hard problem of consciousness. Mind-bending but exciting."
        ),
        activity_count=1,
        l1_category="Mental",
        l2_subcategory="Philosophy",
        expected_skills=[],  # KB discovery test — no roster match expected
        excluded_skills=["Physical Health", "Cardio Endurance", "Meditation", "Restorative Leisure"],
        acceptable_related=["Philosophy", "Philosophy Of Mind", "Analytical Thinking", "Mental Wellbeing"],
        notes="6h study MUST NOT trigger physical, meditation, or leisure skills.",
    ),
    # ── Mental / Positive ───────────────────────────────────────────────────
    EvalEntry(
        id="ment_01_meditate",
        description="20min mindfulness meditation — should detect Meditation",
        content=(
            "Did 20 minutes of mindfulness meditation this morning, "
            "focusing on my breath and body sensations. "
            "Felt calm and centred heading into the day."
        ),
        activity_count=1,
        l1_category="Mental",
        l2_subcategory="Mindfulness",
        expected_skills=["Meditation"],
        excluded_skills=["Physical Health", "Cardio Endurance"],
        acceptable_related=["Mindfulness", "Breathwork", "Mental Wellbeing"],
    ),
    EvalEntry(
        id="ment_02_journal",
        description="Anxiety journaling — should detect Mental Wellbeing",
        content=(
            "Spent 30 minutes journaling about my anxiety around the project deadline. "
            "Wrote down my worst-case fears and then reasoned through why they were unlikely. "
            "Felt lighter afterward."
        ),
        activity_count=1,
        l1_category="Mental",
        l2_subcategory="Emotional Regulation",
        expected_skills=["Mental Wellbeing"],
        excluded_skills=["Physical Health", "Cardio Endurance", "Meditation"],
        acceptable_related=["Emotional Regulation", "Cognitive Reappraisal", "Journaling"],
    ),
    # ── Mental / Negative ───────────────────────────────────────────────────
    EvalEntry(
        id="ment_neg_01",
        description="3h deep focus coding (flow) — must NOT trigger Meditation",
        content=(
            "Worked in deep focus mode for 3 hours on the codebase. "
            "No distractions, just flow state. "
            "Solved a really tricky concurrency bug."
        ),
        activity_count=1,
        l1_category="Professional",
        l2_subcategory="Programming",
        expected_skills=["Programming"],
        excluded_skills=["Meditation", "Physical Health"],
        notes="Focused coding / flow state MUST NOT trigger Meditation.",
    ),
    # ── Professional ────────────────────────────────────────────────────────
    EvalEntry(
        id="prof_01_code",
        description="Python auth module — should detect Programming",
        content=(
            "Spent 3 hours implementing the authentication module in Python. "
            "Fixed a tricky JWT token expiry bug that had been eluding me. "
            "Also added unit tests for the new flows."
        ),
        activity_count=1,
        l1_category="Professional",
        l2_subcategory="Programming",
        expected_skills=["Programming"],
        excluded_skills=["Physical Health", "Meditation", "Restorative Leisure"],
        acceptable_related=["Backend Development", "Test-Driven Development"],
    ),
    EvalEntry(
        id="prof_02_meeting",
        description="Standup + 1:1 — should detect Leadership and Communication",
        content=(
            "Led the weekly standup for the team of 6, then had a 1:1 with the "
            "junior developer to review their PR and unblock them on the database migration."
        ),
        activity_count=1,
        l1_category="Professional",
        l2_subcategory="Leadership",
        expected_skills=["Leadership", "Communication"],
        excluded_skills=["Physical Health", "Meditation"],
        acceptable_related=["Mentoring", "Team Facilitation"],
    ),
    EvalEntry(
        id="prof_03_finance",
        description="Portfolio rebalancing — KB discovery (no roster match)",
        content=(
            "Reviewed the Q1 portfolio allocation today. "
            "Rebalanced from 70/30 equity-bond to 65/35 given increased volatility signals. "
            "Calculated the expected Sharpe ratio changes."
        ),
        activity_count=1,
        l1_category="Professional",
        l2_subcategory="Finance",
        expected_skills=[],  # KB discovery — should find Finance/Investing skills
        excluded_skills=["Physical Health", "Meditation", "Communication"],
        acceptable_related=["Asset Allocation", "Financial Planning", "Risk Management"],
        notes="Should discover from KB, not match roster skills.",
    ),
    # ── Social ──────────────────────────────────────────────────────────────
    EvalEntry(
        id="soc_01_mentor",
        description="Active listening / mentoring coffee chat",
        content=(
            "Had coffee with a new colleague who joined last month. "
            "Spent an hour listening to their concerns about fitting into the team culture "
            "and shared some of my own early experiences. They seemed really relieved."
        ),
        activity_count=1,
        l1_category="Social",
        l2_subcategory="Conversation",
        expected_skills=["Communication"],
        excluded_skills=["Physical Health", "Meditation"],
        acceptable_related=["Active Listening", "Mentoring", "Empathy"],
    ),
    EvalEntry(
        id="soc_02_conflict",
        description="Assertive conversation with manager",
        content=(
            "Had a difficult conversation with my manager about the project scope creep. "
            "I stayed calm, presented my case clearly and asked for a written agreement "
            "on priorities. Felt assertive but respectful."
        ),
        activity_count=1,
        l1_category="Social",
        l2_subcategory="Assertiveness",
        expected_skills=["Communication"],
        excluded_skills=["Physical Health", "Meditation", "Restorative Leisure"],
        acceptable_related=["Assertiveness", "Conflict Resolution", "Negotiation"],
    ),
    # ── Creative ────────────────────────────────────────────────────────────
    EvalEntry(
        id="cre_01_write",
        description="1500-word short story chapter — should detect Creative Writing",
        content=(
            "Drafted the opening chapter of my short story today, about 1500 words. "
            "Really hit a flow state around the 45-minute mark and the dialogue started "
            "writing itself. Excited about where it is going."
        ),
        activity_count=1,
        l1_category="Creative",
        l2_subcategory="Writing",
        expected_skills=["Creative Writing"],
        excluded_skills=["Physical Health", "Meditation", "Programming"],
        acceptable_related=["Fiction Writing", "Storytelling"],
    ),
    EvalEntry(
        id="cre_02_music",
        description="45min guitar practice — should detect Music",
        content=(
            "Practiced guitar for 45 minutes this evening. "
            "Worked through the fingerpicking patterns from last week's lesson "
            "and finally nailed the transition in the chorus section."
        ),
        activity_count=1,
        l1_category="Creative",
        l2_subcategory="Music",
        expected_skills=["Music"],
        excluded_skills=["Physical Health", "Meditation"],
        acceptable_related=["Guitar", "Instrumental Practice", "Music Theory"],
    ),
    # ── Adventure ───────────────────────────────────────────────────────────
    EvalEntry(
        id="adv_01_hike",
        description="12km ridge trail with map navigation — should detect Adventure",
        content=(
            "Hiked the ridge trail today, about 12km with 600m of elevation. "
            "The GPS app died midway so I navigated using a paper map for the last 4km. "
            "Made it without getting lost."
        ),
        activity_count=1,
        l1_category="Adventure",
        l2_subcategory="Exploration",
        expected_skills=["Adventure"],
        excluded_skills=["Meditation", "Physical Health"],
        acceptable_related=["Navigation", "Hiking", "Outdoor Skills", "Cardio Endurance"],
    ),
]

# ---------------------------------------------------------------------------
# TWO-ACTIVITY ENTRIES  (8 entries — 30% of corpus)
# ---------------------------------------------------------------------------

TWO_ACTIVITY: list[EvalEntry] = [
    EvalEntry(
        id="two_01_code_run",
        description="Morning run + afternoon API refactor",
        content=(
            "Morning 5k run along the canal, paced well, felt strong. "
            "Then spent the afternoon refactoring the payment API in Python — "
            "extracted several services and improved the test coverage significantly."
        ),
        activity_count=2,
        l1_category="Physical",
        l2_subcategory="Cardio Endurance",
        expected_skills=["Cardio Endurance", "Programming"],
        excluded_skills=["Meditation", "Restorative Leisure"],
        acceptable_related=["Aerobic Conditioning", "API Design", "Backend Development"],
    ),
    EvalEntry(
        id="two_02_meditate_write",
        description="Guided meditation + essay writing",
        content=(
            "Started the day with 15 minutes of guided breathing meditation, "
            "felt really grounded. Then wrote 800 words of the essay on collective "
            "decision making. Good productive morning."
        ),
        activity_count=2,
        l1_category="Mental",
        l2_subcategory="Mindfulness",
        expected_skills=["Meditation", "Creative Writing"],
        excluded_skills=["Physical Health", "Cardio Endurance"],
        acceptable_related=["Mindfulness", "Academic Writing", "Argumentation"],
    ),
    EvalEntry(
        id="two_03_meeting_gym",
        description="Sprint planning + leg day gym session",
        content=(
            "Morning sprint planning with the team — I facilitated the session and we got "
            "through the full backlog review. "
            "Then evening gym: leg day with squats, lunges, and calf raises."
        ),
        activity_count=2,
        l1_category="Professional",
        l2_subcategory="Leadership",
        expected_skills=["Leadership", "Physical Health"],
        excluded_skills=["Meditation", "Restorative Leisure"],
        acceptable_related=["Team Facilitation", "Strength Training", "Cardio Endurance"],
    ),
    EvalEntry(
        id="two_04_study_journal",
        description="Marcus Aurelius reading + journaling (NOT Meditation)",
        content=(
            "Read two chapters of Meditations by Marcus Aurelius. "
            "Took notes on the stoic concepts of amor fati and memento mori, "
            "then journaled for 20 minutes connecting these ideas to a current work challenge."
        ),
        activity_count=2,
        l1_category="Mental",
        l2_subcategory="Philosophy",
        expected_skills=["Mental Wellbeing"],
        excluded_skills=["Physical Health", "Cardio Endurance", "Meditation"],
        acceptable_related=["Philosophy", "Stoicism", "Journaling", "Cognitive Reappraisal"],
        notes="Reading Stoicism is NOT Meditation. Journaling here is reflective, not mindfulness practice.",
    ),
    EvalEntry(
        id="two_05_music_social",
        description="Open mic performance + supporting other performers",
        content=(
            "Played three songs at the open mic tonight — two originals and a cover. "
            "Stayed for the whole evening to watch other performers "
            "and gave encouraging feedback between acts."
        ),
        activity_count=2,
        l1_category="Creative",
        l2_subcategory="Music",
        expected_skills=["Music", "Communication"],
        excluded_skills=["Physical Health", "Meditation"],
        acceptable_related=["Performance", "Community Building", "Guitar"],
    ),
    EvalEntry(
        id="two_06_hike_photo",
        description="Coastal hike + landscape photography",
        content=(
            "Hiked the coastal path for about 8km and spent time photographing "
            "the cliff formations and tide pools along the way. "
            "Got some really striking compositions with the morning light."
        ),
        activity_count=2,
        l1_category="Adventure",
        l2_subcategory="Exploration",
        expected_skills=["Adventure"],
        excluded_skills=["Meditation", "Cardio Endurance"],
        acceptable_related=["Photography", "Hiking", "Visual Arts", "Outdoor Skills", "Creative Writing"],
        notes="Photography maps to Creative; hiking maps to Adventure. Cardio not expected — hike not framed as exercise.",
    ),
    EvalEntry(
        id="two_neg_01",
        description="4h coding + 3h algorithms study — no physical, no meditation",
        content=(
            "Really productive day: 4 hours coding the new dashboard in the morning, "
            "then 3 hours studying algorithms and data structures from Skiena's book "
            "in the afternoon."
        ),
        activity_count=2,
        l1_category="Professional",
        l2_subcategory="Programming",
        expected_skills=["Programming"],
        excluded_skills=["Physical Health", "Cardio Endurance", "Meditation", "Restorative Leisure"],
        acceptable_related=["Algorithms", "Backend Development", "Computer Science"],
        notes="No physical or meditation despite many hours of focused work.",
    ),
    EvalEntry(
        id="two_07_travel_social",
        description="Travel planning + dinner with old friends",
        content=(
            "Spent the afternoon planning my solo trip to Japan — itinerary across Kyoto, "
            "Tokyo, and Osaka, transport options, and booked accommodation. "
            "In the evening had dinner with university friends, first time seeing them in months."
        ),
        activity_count=2,
        l1_category="Adventure",
        l2_subcategory="Exploration",
        expected_skills=["Communication"],
        excluded_skills=["Physical Health", "Meditation", "Programming"],
        acceptable_related=["Travel Planning", "Adventure", "Adaptability"],
        notes="Planning only (no physical). Social component covers Communication.",
    ),
]

# ---------------------------------------------------------------------------
# THREE-ACTIVITY ENTRIES  (6 entries — 20% of corpus)
# ---------------------------------------------------------------------------

THREE_ACTIVITY: list[EvalEntry] = [
    EvalEntry(
        id="three_01_full_day",
        description="Morning run + Python pipeline work + evening guitar",
        content=(
            "Morning 5k run, good pace, felt energised. "
            "Then 3 hours working on the Python data pipeline — "
            "fixed the transformation logic and added comprehensive error handling. "
            "In the evening practiced guitar for 40 minutes, working on chord transitions."
        ),
        activity_count=3,
        l1_category="Physical",
        l2_subcategory="Cardio Endurance",
        expected_skills=["Cardio Endurance", "Programming", "Music"],
        excluded_skills=["Meditation", "Restorative Leisure"],
        acceptable_related=["Aerobic Conditioning", "Backend Development", "Guitar"],
    ),
    EvalEntry(
        id="three_02_social_day",
        description="Meditation + team retro + dinner with friends",
        content=(
            "Started with 20 minutes of body scan meditation, very calm. "
            "Then facilitated the team retrospective — great discussion about process improvements. "
            "Ended the day with dinner with my university friends, really nice to reconnect."
        ),
        activity_count=3,
        l1_category="Mental",
        l2_subcategory="Mindfulness",
        expected_skills=["Meditation", "Leadership", "Communication"],
        excluded_skills=["Physical Health", "Cardio Endurance"],
        acceptable_related=["Mindfulness", "Team Facilitation", "Mental Wellbeing"],
    ),
    EvalEntry(
        id="three_03_adventure",
        description="Kayaking + camp setup + fire cooking and navigation",
        content=(
            "Kayaked 12km on the river in the morning, hit some class II rapids. "
            "Set up camp in the afternoon — pitched the tent, collected firewood. "
            "Cooked a full meal on the fire and used a compass and topo map "
            "to plan tomorrow's route."
        ),
        activity_count=3,
        l1_category="Adventure",
        l2_subcategory="Outdoor Skills",
        expected_skills=["Adventure"],
        excluded_skills=["Meditation", "Physical Health"],
        acceptable_related=["Kayaking", "Camping", "Navigation", "Outdoor Skills", "Cardio Endurance"],
        notes="Three distinct adventure activities — expect multiple KB skill discoveries.",
    ),
    EvalEntry(
        id="three_04_creative",
        description="Guitar + short story + watercolour session",
        content=(
            "Morning guitar practice for 30 minutes, focused on the new song structure. "
            "After lunch wrote 600 words of the short story, found some good dialogue. "
            "Late afternoon watercolour session — painted the view from the balcony."
        ),
        activity_count=3,
        l1_category="Creative",
        l2_subcategory="Music",
        expected_skills=["Music", "Creative Writing"],
        excluded_skills=["Physical Health", "Meditation", "Programming"],
        acceptable_related=["Guitar", "Fiction Writing", "Visual Arts", "Drawing"],
    ),
    EvalEntry(
        id="three_05_pro_phys",
        description="Standup + code review + yoga recovery session",
        content=(
            "Led the daily standup and then spent 2h doing code review for the team's PRs. "
            "In the evening did a 30 minute yoga session to stretch and recover — "
            "my lower back has been tight all week."
        ),
        activity_count=3,
        l1_category="Professional",
        l2_subcategory="Leadership",
        expected_skills=["Leadership", "Programming", "Physical Health"],
        excluded_skills=["Meditation", "Restorative Leisure"],
        acceptable_related=["Team Facilitation", "Code Review", "Flexibility", "Recovery"],
        notes="Code review counts as Programming practice. Yoga counts as Physical Health (explicit physical activity).",
    ),
    EvalEntry(
        id="three_06_mental",
        description="Meditation + philosophy study + therapy session",
        content=(
            "20 minutes of focused breathing meditation in the morning. "
            "Then 2 hours reading Nietzsche and taking notes on eternal recurrence. "
            "Ended the day with a therapy session where I unpacked some childhood patterns."
        ),
        activity_count=3,
        l1_category="Mental",
        l2_subcategory="Mindfulness",
        expected_skills=["Meditation", "Mental Wellbeing"],
        excluded_skills=["Physical Health", "Cardio Endurance"],
        acceptable_related=["Philosophy", "Emotional Regulation", "Cognitive Reappraisal"],
        notes="Philosophy reading and therapy are distinct from Meditation (which requires explicit meditation language).",
    ),
]

# ---------------------------------------------------------------------------
# Full corpus
# ---------------------------------------------------------------------------

EVAL_CORPUS: list[EvalEntry] = SINGLE_ACTIVITY + TWO_ACTIVITY + THREE_ACTIVITY
