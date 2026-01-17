"""
colors.py

ANSI color utilities for terminal output.
Shared across rtree, locr, and gitmig subcommands.
"""


class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"

    # Foreground Colors
    GREY = "\033[90m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    # Cursor Control
    HIDE_CURSOR = "\033[?25l"
    SHOW_CURSOR = "\033[?25h"

    @staticmethod
    def style(text: str, color: str, enabled: bool = True) -> str:
        """Apply ANSI color to text if enabled."""
        if not enabled:
            return text
        return f"{color}{text}{Colors.RESET}"
