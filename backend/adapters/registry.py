"""
Notes adapter registry.
Set NOTES_ADAPTER in your .env to select where notes go.
"""

import os
from typing import Protocol
from summarizer import Note


class NotesAdapter(Protocol):
    def send(self, note: Note) -> None: ...


def get_adapter() -> NotesAdapter:
    adapter_name = os.getenv("NOTES_ADAPTER", "apple_notes").lower()

    if adapter_name == "apple_notes":
        from adapters.apple_notes import AppleNotesAdapter
        return AppleNotesAdapter()
    elif adapter_name == "notion":
        from adapters.notion import NotionAdapter
        return NotionAdapter()
    elif adapter_name == "obsidian":
        from adapters.obsidian import ObsidianAdapter
        return ObsidianAdapter()
    elif adapter_name == "email":
        from adapters.email_adapter import EmailAdapter
        return EmailAdapter()
    elif adapter_name == "craft":
        from adapters.craft import CraftAdapter
        return CraftAdapter()
    else:
        raise ValueError(
            f"Unknown NOTES_ADAPTER: '{adapter_name}'. "
            "Valid options: apple_notes, notion, obsidian, email, craft"
        )
