"""
Load local secrets from a .env file into environment variables.

  - .env lives next to this file, is listed in .gitignore and is never served by server.py.
  - Values already set in the environment (e.g. GitHub Actions secrets) always win.
  - Format: KEY=value per line; blank lines and lines starting with # are ignored;
    values may be wrapped in single or double quotes.
"""

import os

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_env(path: str = ENV_FILE) -> list[str]:
    """Read KEY=value pairs from `path` into os.environ. Returns the keys that were loaded."""
    if not os.path.isfile(path):
        return []

    loaded = []
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.removeprefix("export ").strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key and value and not os.environ.get(key):
                os.environ[key] = value
                loaded.append(key)
    return loaded
