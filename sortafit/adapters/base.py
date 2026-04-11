"""Sorta.Fit abstract board adapter interface."""
from abc import ABC, abstractmethod


class BoardAdapter(ABC):
    """Interface that all board adapters must implement.

    Port of the board_* bash function interface.
    """

    @abstractmethod
    def get_cards_in_status(self, status: str, max_count: int = 10, start_at: int = 0) -> list[str]:
        """Return issue IDs in the given status."""

    @abstractmethod
    def get_card_key(self, issue_id: str) -> str:
        """Return the human-readable key (e.g., PROJ-123)."""

    @abstractmethod
    def get_card_title(self, issue_key: str) -> str:
        """Return just the title/summary text."""

    @abstractmethod
    def get_card_type(self, issue_key: str) -> str:
        """Return the issue type (Bug, Story, Task, etc.)."""

    @abstractmethod
    def get_card_description(self, issue_key: str) -> str:
        """Return the description as markdown text."""

    @abstractmethod
    def get_card_comments(self, issue_key: str) -> str:
        """Return all comments as formatted text."""

    @abstractmethod
    def update_description(self, issue_key: str, markdown: str) -> None:
        """Replace the card description with the given markdown."""

    @abstractmethod
    def add_comment(self, issue_key: str, comment: str) -> None:
        """Add a comment to the card."""

    @abstractmethod
    def transition(self, issue_key: str, transition_id: str) -> None:
        """Move the card using the given transition ID."""

    @abstractmethod
    def discover(self) -> str:
        """Return available statuses and transitions for setup."""

    def get_card_summary(self, issue_key: str) -> str:
        """Return formatted summary. Default implementation."""
        return f"Key: {issue_key}\nSummary: {self.get_card_title(issue_key)}"

    def get_card_status(self, issue_key: str) -> str:
        """Return status name|status_id. Optional — used by deps."""
        return ""

    def get_card_links(self, issue_key: str) -> str:
        """Return dependency links. Optional — used by deps."""
        return ""
