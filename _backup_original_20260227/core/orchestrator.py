"""
Main orchestrator for journal entry processing.

This module provides the JournalProcessingOrchestrator class that ties together
all Week 2 systems: XP calculation, quest matching, and title awarding.

The orchestrator:
1. Coordinates the full processing pipeline for journal entries
2. Handles categorization (stubbed for Week 2, AI in Week 3)
3. Distributes XP to themes and skills
4. Matches entries against active quests
5. Checks and awards titles on level-ups
6. Provides robust error handling with retry logic

Usage:
    from app.core.orchestrator import JournalProcessingOrchestrator
    from app.core.events import get_event_bus
    from app.core.config_loader import get_config

    orchestrator = JournalProcessingOrchestrator(
        event_bus=get_event_bus(),
        config=get_config(),
    )

    # Process a journal entry
    result = orchestrator.process_entry(db, entry)
    # result = {
    #     "entry_id": "...",
    #     "status": "completed",
    #     "categories": {...},
    #     "xp_summary": {...},
    #     "quests_updated": [...],
    #     "titles_awarded": [...],
    # }
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.core.config_loader import ConfigLoader
from app.core.events import EventBus
from app.core.quests.matcher import QuestMatcher
from app.core.titles.awarder import TitleAwarder
from app.core.xp.calculator import XPCalculator
from app.core.xp.strategies import EqualDistributor
from app.utils.logging_config import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.journal_entry import JournalEntry

logger = get_logger(__name__)

# Maximum retry attempts before marking an entry as failed
MAX_RETRY_COUNT = 3


class MissingTranscriptError(ValueError):
    """Raised when a voice journal entry has no transcript content."""


class JournalProcessingOrchestrator:
    """
    Main orchestrator for processing journal entries.

    Coordinates all Week 2 systems: XP distribution, quest matching,
    and title awarding. Provides event-driven architecture for loose
    coupling between game mechanics.

    Attributes:
        event_bus: EventBus for publishing and subscribing to events
        config: ConfigLoader for game balance settings
        xp_calculator: XPCalculator for distributing XP
        quest_matcher: QuestMatcher for checking quest completion
        title_awarder: TitleAwarder for checking and awarding titles
        ai_categorizer: AI categorizer (Week 3 stub, currently None)
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigLoader,
    ) -> None:
        """
        Initialize the orchestrator.

        Args:
            event_bus: EventBus instance for event-driven communication
            config: ConfigLoader instance for game balance settings
        """
        self._event_bus = event_bus
        self._config = config

        # Initialize core systems
        self._xp_calculator = XPCalculator(
            strategy=EqualDistributor(),
            event_bus=event_bus,
            config=config,
        )
        self._quest_matcher = QuestMatcher(event_bus)
        self._title_awarder = TitleAwarder(event_bus)

        # Week 3 AI categorizer stub
        self._ai_categorizer: Any = None

        # Register event listeners
        self._register_listeners()

        logger.info("JournalProcessingOrchestrator initialized")

    def process_entry(
        self,
        db: "Session",
        entry: "JournalEntry",
    ) -> dict[str, Any]:
        """
        Main entry point for processing a journal entry.

        Runs the full processing pipeline:
        1. Update status to "processing"
        2. Categorize entry (stub for Week 2)
        3. Distribute XP based on categories
        4. Match entry against active quests
        5. Check for title unlocks
        6. Mark as completed or handle errors

        Args:
            db: Database session
            entry: The JournalEntry to process

        Returns:
            Processing summary with results from each stage
        """
        # Mark entry as processing
        entry.processing_status = "processing"
        entry.processing_error = None
        db.commit()

        try:
            # Step 1: Categorize entry (Week 2 stub)
            categories = self._stub_categorize(entry)
            entry.ai_categories = categories
            entry.ai_processed = True

            # Step 2: Distribute XP
            xp_summary = self._xp_calculator.process_journal_entry(
                db, entry, categories
            )

            # Step 3: Match against quests
            updated_quests = self._quest_matcher.match_journal_entry(db, entry)
            quests_updated = [
                {
                    "quest_id": q.id,
                    "quest_name": q.name,
                    "progress": q.completion_progress,
                    "status": q.status,
                }
                for q in updated_quests
            ]

            # Step 4: Check for title unlocks
            newly_awarded = self._title_awarder.check_user_unlocks(db, entry.user_id)
            titles_awarded = [
                {
                    "title_id": ut.id,
                    "title_name": ut.title_template.name if ut.title_template else "Unknown",
                }
                for ut in newly_awarded
            ]

            # Mark as completed
            entry.processing_status = "completed"
            db.commit()

            result = {
                "entry_id": entry.id,
                "status": "completed",
                "categories": categories,
                "xp_summary": xp_summary,
                "quests_updated": quests_updated,
                "titles_awarded": titles_awarded,
            }

            logger.info(
                "Journal entry processed successfully",
                entry_id=entry.id,
                total_xp=xp_summary.get("total_xp", 0),
                quests_updated=len(quests_updated),
                titles_awarded=len(titles_awarded),
            )

            return result

        except Exception as e:
            self._handle_processing_error(db, entry, e)
            return {
                "entry_id": entry.id,
                "status": entry.processing_status,
                "error": str(e),
            }

    def _register_listeners(self) -> None:
        """
        Register event listeners for the orchestrator.

        Subscribes to:
        - journal_entry.created: Trigger processing
        - xp.awarded: Update stats, check achievements
        - theme.leveled_up: Check title unlocks
        - skill.leveled_up: Check title unlocks
        - quest.completed: Award quest rewards
        """
        self._event_bus.subscribe("journal_entry.created", self._on_entry_created)
        self._event_bus.subscribe("xp.awarded", self._on_xp_awarded)
        self._event_bus.subscribe("theme.leveled_up", self._on_level_up)
        self._event_bus.subscribe("skill.leveled_up", self._on_level_up)
        self._event_bus.subscribe("quest.completed", self._on_quest_completed)

        logger.debug("Event listeners registered")

    def _on_entry_created(self, payload: dict[str, Any]) -> None:
        """
        Handle journal_entry.created event.

        This is typically called from the API layer after a new entry is
        persisted. In async scenarios, this could trigger background processing.

        Args:
            payload: Event payload with entry_id and user_id
        """
        entry_id = payload.get("entry_id")
        logger.debug(
            "Received journal_entry.created event",
            entry_id=entry_id,
        )
        # Note: Actual processing should be triggered from the API layer
        # with a proper database session. This handler is for logging
        # and potential async processing in the future.

    def _on_xp_awarded(self, payload: dict[str, Any]) -> None:
        """
        Handle xp.awarded event.

        Could trigger:
        - Achievement checks
        - Stats updates
        - Streak tracking

        Args:
            payload: Event payload with user_id, amount, source, target
        """
        user_id = payload.get("user_id")
        amount = payload.get("amount", 0)
        target_type = payload.get("target_type")
        target_id = payload.get("target_id")

        logger.debug(
            "XP awarded",
            user_id=user_id,
            amount=amount,
            target_type=target_type,
            target_id=target_id,
        )
        # Future: Update user stats, check XP-based achievements

    def _on_level_up(self, payload: dict[str, Any]) -> None:
        """
        Handle theme.leveled_up and skill.leveled_up events.

        Triggers title unlock checks for level-based conditions.

        Args:
            payload: Event payload with user_id and level info
        """
        user_id = payload.get("user_id")
        new_level = payload.get("new_level")

        logger.debug(
            "Level up detected",
            user_id=user_id,
            new_level=new_level,
        )
        # Note: Title checks are already done in process_entry.
        # This handler is for level-ups triggered outside of journal processing
        # (e.g., practice time, manual XP grants).

    def _on_quest_completed(self, payload: dict[str, Any]) -> None:
        """
        Handle quest.completed event.

        Awards quest rewards (XP, coins) and triggers related checks.

        Args:
            payload: Event payload with quest details and rewards
        """
        user_id = payload.get("user_id")
        quest_id = payload.get("quest_id")
        quest_name = payload.get("quest_name")
        reward_xp = payload.get("reward_xp", 0)
        reward_coins = payload.get("reward_coins", 0)

        logger.info(
            "Quest completed",
            user_id=user_id,
            quest_id=quest_id,
            quest_name=quest_name,
            reward_xp=reward_xp,
            reward_coins=reward_coins,
        )
        # Future: Award XP to user's general pool, add coins to wallet
        # Could also trigger title checks for quest-based conditions

    def _stub_categorize(self, entry: "JournalEntry") -> dict[str, Any]:
        """
        Stub categorization for Week 2.

        Returns empty categories. Will be replaced with AI categorization in
        Week 3.

        Voice entries require a transcript in `content`. Missing transcript
        content is treated as a non-retryable processing error.

        Args:
            entry: The journal entry to categorize

        Returns:
            Empty category dict with expected structure
        """
        if entry.entry_type in {"voice", "voice_transcription"} and not (entry.content or "").strip():
            raise MissingTranscriptError("Voice entry has no transcript to process")

        return {
            "themes": [],
            "skills": [],
            "sentiment": "neutral",
        }

    def _handle_processing_error(
        self,
        db: "Session",
        entry: "JournalEntry",
        error: Exception,
    ) -> None:
        """
        Handle processing errors with retry logic.

        - Logs the error
        - Updates entry with error details
        - Increments retry_count
        - Sets status to "pending" for retry if under MAX_RETRY_COUNT
        - Sets status to "failed" if retries exhausted

        Never loses the entry - it's always preserved for debugging.

        Args:
            db: Database session
            entry: The entry that failed processing
            error: The exception that was raised
        """
        entry.retry_count = (entry.retry_count or 0) + 1
        entry.last_retry_at = datetime.utcnow()
        entry.processing_error = str(error)[:500]  # Truncate to fit column

        if isinstance(error, MissingTranscriptError):
            entry.processing_status = "failed"
            logger.error(
                "Journal entry processing failed due to missing transcript",
                entry_id=entry.id,
                retry_count=entry.retry_count,
                error=str(error),
            )
        elif entry.retry_count < MAX_RETRY_COUNT:
            entry.processing_status = "pending"
            logger.warning(
                "Journal entry processing failed, will retry",
                entry_id=entry.id,
                retry_count=entry.retry_count,
                max_retries=MAX_RETRY_COUNT,
                error=str(error),
            )
        else:
            entry.processing_status = "failed"
            logger.error(
                "Journal entry processing failed permanently",
                entry_id=entry.id,
                retry_count=entry.retry_count,
                error=str(error),
                exc_info=True,
            )

        db.commit()

    @property
    def xp_calculator(self) -> XPCalculator:
        """Get the XP calculator instance."""
        return self._xp_calculator

    @property
    def quest_matcher(self) -> QuestMatcher:
        """Get the quest matcher instance."""
        return self._quest_matcher

    @property
    def title_awarder(self) -> TitleAwarder:
        """Get the title awarder instance."""
        return self._title_awarder

    @property
    def ai_categorizer(self) -> Any:
        """Get the AI categorizer instance (None for Week 2)."""
        return self._ai_categorizer

    @ai_categorizer.setter
    def ai_categorizer(self, value: Any) -> None:
        """Set the AI categorizer instance (for Week 3 integration)."""
        self._ai_categorizer = value
