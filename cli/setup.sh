#!/bin/bash

# Install Python dependencies
pip install -r requirements.txt --break-system-packages

# Make CLI executable
chmod +x rpg_life.py

# Create symlink (optional)
# sudo ln -s $(pwd)/rpg_life.py /usr/local/bin/rpg-life

echo "✓ CLI setup complete!"
echo ""
echo "Usage:"
echo "  ./rpg_life.py submit        # Submit journal entry"
echo "  ./rpg_life.py status        # Show current status"
echo "  ./rpg_life.py skills        # List skills"
echo "  ./rpg_life.py quests        # List quests"
echo "  ./rpg_life.py stats         # Detailed statistics"
