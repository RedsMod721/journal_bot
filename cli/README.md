# RPG Life Tracker CLI

Command-line interface for quick journal submissions and status checks.

## Setup
```bash
cd cli
./setup.sh
```

Create `cli/.env`:
```bash
API_BASE_URL=http://localhost:8000
API_PREFIX=/api
USER_ID=<real-user-uuid>
```

## Usage

### Submit Journal Entry
```bash
./rpg_life.py submit
# Or use editor:
./rpg_life.py submit --editor
```

### Check Status
```bash
./rpg_life.py status
```

### View Skills
```bash
./rpg_life.py skills
./rpg_life.py skills --limit 5
./rpg_life.py skills --sort level
```

### View Quests
```bash
./rpg_life.py quests
./rpg_life.py quests --status completed
```

### Detailed Stats
```bash
./rpg_life.py stats
```

## Requirements

- Python 3.8+
- Backend API running on localhost:8000
