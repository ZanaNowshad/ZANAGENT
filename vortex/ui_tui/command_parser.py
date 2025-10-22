"""Slash command parsing utilities."""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class SlashCommand:
    """Represents a parsed slash command."""

    raw: str
    name: str
    args: List[str]
    options: Dict[str, str]

    def option(self, flag: str, default: Optional[str] = None) -> Optional[str]:
        return self.options.get(flag, default)


def parse_slash_command(text: str) -> Optional[SlashCommand]:
    """Parse a slash command entered by the user.

    The parser is intentionally forgiving: it supports ``-k value`` as well as
    ``--flag=value`` syntaxes and preserves positional arguments for downstream
    handlers.
    """

    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    payload = stripped[1:]
    if not payload:
        return None
    try:
        tokens = shlex.split(payload)
    except ValueError:
        # Unbalanced quotes are common while the agent reasons about prompts; in
        # that case we return ``None`` so the UI can surface a friendly error.
        return None
    if not tokens:
        return None
    name = tokens[0]
    args: List[str] = []
    options: Dict[str, str] = {}
    iterator = iter(tokens[1:])
    for token in iterator:
        if token.startswith("-"):
            if "=" in token:
                flag, value = token.split("=", 1)
                options[flag] = value
            else:
                try:
                    value = next(iterator)
                    if value.startswith("-"):
                        options[token] = "true"
                        # Re-process the flag-like token on the next iteration
                        iterator = iter([value, *list(iterator)])
                    else:
                        options[token] = value
                except StopIteration:
                    options[token] = "true"
        else:
            args.append(token)
    return SlashCommand(raw=text, name=name.lower(), args=args, options=options)


__all__ = ["SlashCommand", "parse_slash_command"]
