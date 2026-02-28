"""Compatibility bridge for legacy pytest path expectations."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tests.test_core.test_quests.test_src_quests_module import *  # noqa: F401,F403
