"""
languages.py

Language definitions for lines of code counting.
Contains comment syntax, file extensions, and display colors.
"""

from gtrmrs.core.colors import Colors

# =============================================================================
# Language Definitions
# =============================================================================
LANGUAGES = {
    # Python (Yellow)
    ".py": {
        "name": "Python",
        "color": Colors.YELLOW,
        "single": "#",
        "multi": ('"""', '"""'),
    },
    # Web (Red/Blue/Magenta)
    ".html": {
        "name": "HTML",
        "color": Colors.RED,
        "single": None,
        "multi": ("<!--", "-->"),
    },
    ".css": {
        "name": "CSS",
        "color": Colors.BLUE,
        "single": None,
        "multi": ("/*", "*/"),
    },
    ".scss": {
        "name": "Sass",
        "color": Colors.MAGENTA,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".js": {
        "name": "JavaScript",
        "color": Colors.YELLOW,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".jsx": {
        "name": "JavaScript JSX",
        "color": Colors.YELLOW,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".ts": {
        "name": "TypeScript",
        "color": Colors.BLUE,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".tsx": {
        "name": "TypeScript TSX",
        "color": Colors.BLUE,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".json": {"name": "JSON", "color": Colors.GREY, "single": None, "multi": None},
    # C-Family (Blue/Red)
    ".c": {"name": "C", "color": Colors.BLUE, "single": "//", "multi": ("/*", "*/")},
    ".h": {
        "name": "C Header",
        "color": Colors.BLUE,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".cpp": {
        "name": "C++",
        "color": Colors.BLUE,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".cs": {
        "name": "C#",
        "color": Colors.MAGENTA,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".java": {
        "name": "Java",
        "color": Colors.RED,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    # Systems (Cyan/Red)
    ".go": {"name": "Go", "color": Colors.CYAN, "single": "//", "multi": ("/*", "*/")},
    ".rs": {"name": "Rust", "color": Colors.RED, "single": "//", "multi": ("/*", "*/")},
    ".php": {
        "name": "PHP",
        "color": Colors.MAGENTA,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    # Config/Data (Grey/White/Cyan)
    ".md": {
        "name": "Markdown",
        "color": Colors.WHITE,
        "single": None,
        "multi": None,
    },
    ".yaml": {"name": "YAML", "color": Colors.CYAN, "single": "#", "multi": None},
    ".yml": {"name": "YAML", "color": Colors.CYAN, "single": "#", "multi": None},
    ".toml": {"name": "TOML", "color": Colors.CYAN, "single": "#", "multi": None},
    ".xml": {
        "name": "XML",
        "color": Colors.RED,
        "single": None,
        "multi": ("<!--", "-->"),
    },
    ".sql": {
        "name": "SQL",
        "color": Colors.YELLOW,
        "single": "--",
        "multi": ("/*", "*/"),
    },
    # Scripts
    ".sh": {"name": "Shell", "color": Colors.GREEN, "single": "#", "multi": None},
    ".lua": {
        "name": "Lua",
        "color": Colors.BLUE,
        "single": "--",
        "multi": ("--[[", "]]"),
    },
}
