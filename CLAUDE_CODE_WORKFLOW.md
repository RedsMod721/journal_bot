# CLAUDE CODE WORKFLOW GUIDE
## Working Between Claude.ai and Claude Code in VS Code

**Purpose:** This guide explains how to leverage both Claude.ai (strategic planning) and Claude Code (implementation) effectively for maximum productivity.

---

## 🎭 TWO CLAUDES, TWO ROLES

### Claude.ai (This Conversation - Strategic Partner)
**Use for:**
- 🧠 High-level planning and architecture decisions
- 🔍 Research and analysis (tech stack comparisons, best practices)
- 📊 Project management (roadmap adjustments, risk assessment)
- 🎯 Feature prioritization and scope decisions
- 🐛 Complex debugging strategy (when stuck)
- 📝 Documentation review and feedback

**Strengths:**
- Long-term memory of project context
- Access to web search and research tools
- Strategic thinking and trade-off analysis
- Can see "the forest" (big picture)

---

### Claude Code in VS Code (Implementation Partner)
**Use for:**
- 💻 Writing code (functions, classes, modules)
- 🔨 Refactoring and optimization
- 🧪 Writing tests
- 📦 Installing dependencies and troubleshooting setup
- 🐞 Debugging specific errors (stack traces, syntax issues)
- 🎨 UI/UX implementation
- 📂 File organization and cleanup

**Strengths:**
- Direct file access (can read/write your codebase)
- Faster iteration (no copy-paste needed)
- Context-aware completions (knows your project structure)
- Can run commands in terminal
- Can see "the trees" (implementation details)

---

## 🔄 THE WORKFLOW LOOP

```
┌─────────────────────────────────────────────┐
│   CLAUDE.AI (Strategic Planning)            │
│   - Define next milestone                   │
│   - Break down into tasks                   │
│   - Identify risks/blockers                 │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
          📋 Export Context
          (Copy milestones, 
           requirements, specs)
                  │
                  ▼
┌─────────────────────────────────────────────┐
│   CLAUDE CODE (Implementation)              │
│   - Write code for tasks                    │
│   - Run tests                               │
│   - Debug errors                            │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
          ✅ Checkpoint Reached
          (Feature complete, 
           tests pass, documented)
                  │
                  ▼
┌─────────────────────────────────────────────┐
│   BACK TO CLAUDE.AI                         │
│   - Report progress                         │
│   - Get next milestone                      │
│   - Adjust plan if needed                   │
└─────────────────────────────────────────────┘
```

---

## 📚 CONTEXT TRANSFER: CLAUDE.AI → CLAUDE CODE

### What to Transfer
When starting a new implementation session in Claude Code, provide:

1. **Current Milestone** (from DEVELOPMENT_GUIDE.md)
   - Example: "Week 2, Day 8-9: Title Awarding System"

2. **Specific Tasks** (copy from this conversation or guide)
   - Example: "Implement title unlock condition detection, create AI-powered personalized title award messages"

3. **Relevant Sections from PROJECT_SPECIFICATION.md**
   - Example: "Read the 'Titles' section in PROJECT_SPECIFICATION.md for context"

4. **Any Decisions Made in Claude.ai**
   - Example: "We decided to use Llama 3.2 for categorization, not Mistral"

5. **Current Blockers/Questions**
   - Example: "XP distribution is working, but need to implement level-up celebration animations"

### How to Transfer (Recommended Approach)

**Option A: Reference Docs (Preferred)**
```
In Claude Code chat, say:

"I'm working on Week 2, Day 8-9 of the Development Guide (Title Awarding System).
Please read:
1. PROJECT_SPECIFICATION.md (Titles section)
2. DEVELOPMENT_GUIDE.md (Week 2, Day 8-9 tasks)
3. Current codebase in app/models/title.py

Help me implement the TitleAwarder class."
```

**Option B: Direct Copy-Paste (When Needed)**
```
Copy specific requirements from this conversation and paste into Claude Code:

"I need to implement this unlock condition logic:
- journal_streak: Check if user has X consecutive days
- theme_level: Check if theme reached level Y
- total_journal_entries: Check if user has N total entries

Based on PROJECT_SPECIFICATION.md, implement check_condition() method."
```

---

## 🎯 WHEN TO USE WHICH CLAUDE

### Scenario Decision Tree

#### "I need to decide if we should use React or plain HTML for the MVP"
→ **Claude.ai** - Strategic decision requiring trade-off analysis

#### "How do I implement this specific Python function?"
→ **Claude Code** - Implementation task with file access

#### "I'm getting a SQLAlchemy error when creating a user"
→ **Claude Code** - Debugging specific error with stack trace

#### "Should we push back the MVP deadline or cut features?"
→ **Claude.ai** - Project management decision

#### "I want to refactor the XP calculation logic"
→ **Claude Code** - Code refactoring with context

#### "Is our database schema correct for multi-user scaling?"
→ **Claude.ai** - Architecture review

#### "I need to write tests for the categorizer module"
→ **Claude Code** - Test implementation

#### "We're running over budget on AI calls, what should we do?"
→ **Claude.ai** - Strategic problem-solving

---

## 🚀 MILESTONE WORKFLOW (Detailed Example)

Let's walk through **Week 2, Day 8-9: Title Awarding System** as a complete example.

### Step 1: Planning in Claude.ai (This Conversation)
**You say:**
> "I'm ready to start Week 2, Day 8-9. Can you give me a detailed breakdown?"

**Claude.ai responds:**
> "Week 2, Day 8-9 focuses on the Title Awarding System. Here are the tasks:
> 1. Implement TitleAwarder class with check_condition() method
> 2. Support 3 condition types: journal_streak, theme_level, total_journal_entries
> 3. Generate personalized award messages using AI
> 4. Seed GlobalTitleBank with 10-15 starter titles
> 
> Deliverables: TitleAwarder class tested, 10+ titles seeded, awards display on dashboard
> 
> Key decisions:
> - Use rule-based checking (not AI) for performance
> - AI only generates personalized award text
> - Store unlock conditions as JSON for flexibility
> 
> Ready to implement?"

**You confirm:**
> "Yes, moving to Claude Code now."

---

### Step 2: Implementation in Claude Code

**Open VS Code → Claude Code Chat**

**You say:**
```
I'm implementing the Title Awarding System (Week 2, Day 8-9 of DEVELOPMENT_GUIDE.md).

Context:
- Read PROJECT_SPECIFICATION.md (Titles section) for game mechanics
- Current models are in app/models/title.py (TitleTemplate, UserTitle)
- Need to create app/core/title_awarder.py

Tasks:
1. Implement TitleAwarder class with check_and_award_titles() method
2. Support unlock conditions: journal_streak, theme_level, total_journal_entries
3. Generate personalized award messages (use ollama_client.py)

Start with the TitleAwarder skeleton. Show me the class structure first.
```

**Claude Code responds with code:**
```python
# app/core/title_awarder.py
class TitleAwarder:
    def __init__(self, db: Session):
        self.db = db
    
    def check_and_award_titles(self, user_id: str):
        # Implementation...
```

**You iterate:**
```
Great! Now implement the _check_condition() method for journal_streak.
Reference app/models/journal_entry.py for the JournalEntry model.
```

**Claude Code implements, you test, debug together.**

---

### Step 3: Checkpoint Back to Claude.ai

**After completing tasks, return to this conversation:**

**You report:**
> "✅ Week 2, Day 8-9 complete!
> - TitleAwarder class implemented and tested
> - Supports 3 condition types
> - Seeded 12 starter titles
> - Tested with sample data, titles are awarded correctly
> 
> Issue encountered: AI-generated award messages were too verbose. Fixed by adjusting temperature to 0.5.
> 
> Ready for next milestone?"

**Claude.ai responds:**
> "Excellent! That's ahead of schedule. Let's move to Week 3, Day 10-12: Ollama Integration.
> 
> Before we start, any blockers from Week 2 we should address?"

---

## 💡 PRODUCTIVITY TIPS

### 1. Keep Both Open Side-by-Side
- **Left Monitor:** VS Code with Claude Code (implementation)
- **Right Monitor:** Browser with Claude.ai (planning)

### 2. Use Claude.ai for Morning Planning
- Start each session by reviewing progress in Claude.ai
- Get the day's tasks and priorities
- Then switch to Claude Code for execution

### 3. Use Claude Code for Deep Work
- Once you have clear tasks, minimize distractions
- Work in 1-2 hour focused blocks with Claude Code
- Return to Claude.ai for checkpoint/next milestone

### 4. Document Decisions in Both Places
- Major decisions → Update PROJECT_SPECIFICATION.md (Claude Code can edit it)
- Progress updates → Log in this Claude.ai conversation for tracking

### 5. Use Claude.ai for "Stuck" Moments
- If stuck for >30 minutes in Claude Code → come here
- Describe blocker, get strategic advice
- Return to Claude Code with new approach

---

## 🔧 SETTING UP CLAUDE CODE

### Initial Setup (First Time Only)

1. **Install Claude Code Extension in VS Code**
   - Extensions → Search "Claude Code" → Install
   - Sign in with Anthropic account

2. **Add Project Context Files**
   - Place PROJECT_SPECIFICATION.md in repo root
   - Place DEVELOPMENT_GUIDE.md in repo root
   - Claude Code can now reference these automatically

3. **Configure Claude Code to Read Docs**
   - In .vscode/settings.json, add:
   ```json
   {
     "claude.contextFiles": [
       "PROJECT_SPECIFICATION.md",
       "DEVELOPMENT_GUIDE.md",
       "README.md"
     ]
   }
   ```

4. **Test Integration**
   - Ask Claude Code: "Read PROJECT_SPECIFICATION.md and summarize the core game mechanics"
   - Verify it responds with accurate info

---

## 📝 QUICK REFERENCE COMMANDS

### In Claude.ai (This Conversation)
- "Show me Week X tasks from the development guide"
- "I'm stuck on [feature], help me debug the approach"
- "Should we prioritize [feature A] or [feature B]?"
- "Review my progress and suggest next steps"
- "Research best practices for [topic]"

### In Claude Code (VS Code)
- "Implement [function name] based on [file/spec]"
- "Write tests for [module]"
- "Debug this error: [paste stack trace]"
- "Refactor [code block] to be more efficient"
- "Create [new file] following the project structure"

---

## ⚠️ COMMON PITFALLS TO AVOID

### ❌ Don't: Ask Claude Code for Strategic Decisions
**Bad:** "Should we use React or Vue for the frontend?"
**Why:** Claude Code doesn't have full project context for trade-off analysis
**Fix:** Ask Claude.ai instead

### ❌ Don't: Paste Large Code Blocks into Claude.ai
**Bad:** Copy 200 lines of code into this chat for debugging
**Why:** Claude.ai can't edit files directly, you'll waste time copy-pasting
**Fix:** Debug in Claude Code (it has file access)

### ❌ Don't: Forget to Update PROJECT_SPECIFICATION.md
**Bad:** Make major architecture changes without documenting
**Why:** Claude Code (and future you) will get confused
**Fix:** Update specs in Claude Code, report change in Claude.ai

### ❌ Don't: Switch Tools Mid-Task
**Bad:** Start implementing in Claude Code, jump to Claude.ai for one line, back to Claude Code
**Why:** Context switching kills productivity
**Fix:** Finish the task in one tool, then checkpoint

---

## 🎯 SUCCESS METRICS

**You're using the workflow correctly if:**
- ✅ Each coding session has clear tasks (from DEVELOPMENT_GUIDE.md)
- ✅ You complete 1-2 milestones per week
- ✅ You rarely copy-paste code between tools
- ✅ PROJECT_SPECIFICATION.md stays up-to-date
- ✅ You checkpoint progress in Claude.ai regularly (every 2-3 days)

**Warning signs you need to adjust:**
- ⚠️ Feeling lost or directionless (need more planning in Claude.ai)
- ⚠️ Spending >30 min copy-pasting (use Claude Code more)
- ⚠️ Implementing features not in the plan (scope creep, revisit Claude.ai)
- ⚠️ Can't remember why you made a decision (document better)

---

## 📊 RECOMMENDED WEEKLY RHYTHM

### Monday (Planning Day)
- **Claude.ai:** Review last week's progress, plan this week's milestones
- **Claude.ai:** Identify any scope adjustments needed
- **Output:** Clear task list for the week

### Tuesday-Thursday (Execution Days)
- **Claude Code:** Deep work on implementation
- **Check-in with Claude.ai:** Brief status update, get unstuck if needed
- **Output:** Code, tests, progress on milestones

### Friday (Integration & Review)
- **Claude Code:** Integration testing, bug fixes
- **Claude.ai:** Review week's achievements, plan next week
- **Output:** Working features, updated documentation

### Saturday-Sunday (Optional)
- **Light coding in Claude Code** if inspired
- **Research in Claude.ai** for next week's challenges

---

**END OF WORKFLOW GUIDE**

_This workflow is designed for solo development with AI assistance. Adjust as needed based on what works for you!_
