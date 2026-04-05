"""
languages.py

Language definitions for lines of code counting.
Contains comment syntax, file extensions, and display colors.
"""

import os

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
        "multi": None,
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
    ".cc": {
        "name": "C++",
        "color": Colors.BLUE,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".cxx": {
        "name": "C++",
        "color": Colors.BLUE,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".hpp": {
        "name": "C++ Header",
        "color": Colors.BLUE,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".hh": {
        "name": "C++ Header",
        "color": Colors.BLUE,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".hxx": {
        "name": "C++ Header",
        "color": Colors.BLUE,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".proto": {
        "name": "Protocol Buffers",
        "color": Colors.CYAN,
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
    ".kt": {
        "name": "Kotlin",
        "color": Colors.MAGENTA,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".kts": {
        "name": "Kotlin Script",
        "color": Colors.MAGENTA,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".gradle": {
        "name": "Gradle",
        "color": Colors.GREEN,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".aidl": {
        "name": "AIDL",
        "color": Colors.CYAN,
        "single": "//",
        "multi": ("/*", "*/"),
    },
    ".pro": {
        "name": "ProGuard",
        "color": Colors.YELLOW,
        "single": "#",
        "multi": None,
    },
    ".properties": {
        "name": "Properties",
        "color": Colors.WHITE,
        "single": "#",
        "multi": None,
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

# Aliases share a definition so counting and language totals remain consistent.
LANGUAGES[".pyi"] = LANGUAGES[".py"]
LANGUAGES[".sass"] = LANGUAGES[".scss"]
for extension in (".bash", ".zsh"):
    LANGUAGES[extension] = LANGUAGES[".sh"]
LANGUAGES[".swift"] = {
    "name": "Swift", "color": Colors.RED, "single": "//", "multi": ("/*", "*/"),
}
LANGUAGES[".ps1"] = {
    "name": "PowerShell", "color": Colors.BLUE, "single": "#", "multi": ("<#", "#>"),
}
for extension in (".bat", ".cmd"):
    LANGUAGES[extension] = {
        "name": "Batch", "color": Colors.GREEN, "single": None, "multi": None,
    }

FILENAMES = {
    "Dockerfile": {"name": "Dockerfile", "color": Colors.CYAN, "single": "#", "multi": None},
}


def language_for(path):
    """Recognize documented extensions and exact special filenames."""
    return FILENAMES.get(os.path.basename(path)) or LANGUAGES.get(os.path.splitext(path)[1].lower())
