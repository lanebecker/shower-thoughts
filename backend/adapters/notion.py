"""
Notion adapter — creates a new page in a database.

Required env vars:
  NOTION_API_KEY        — your Notion integration token
  NOTION_DATABASE_ID    — the database to write pages into
"""

import os
import logging
import requests
from summarizer import Note

log = logging.getLogger(__name__)


class NotionAdapter:
    def send(self, note: Note) -> None:
        api_key = os.getenv("NOTION_API_KEY", "")
        db_id   = os.getenv("NOTION_DATABASE_ID", "")
        if not api_key or not db_id:
            raise EnvironmentError("Set NOTION_API_KEY and NOTION_DATABASE_ID")
        headers = {
            "Authorization":  f"Bearer {api_key}",
            "Content-Type":   "application/json",
            "Notion-Version": "2022-06-28",
        }
        page = {
            "parent": {"database_id": db_id},
            "properties": {
                "Name":     {"title":     [{"text": {"content": f"🚿 {note.title}"}}]},
                "Summary":  {"rich_text": [{"text": {"content": note.summary}}]},
                "Tags":     {"multi_select": [{"name": t} for t in note.tags]},
                "Recorded": {"date": {"start": note.recorded_at}},
            },
            "children": [{"object": "block", "type": "paragraph",
                          "paragraph": {"rich_text": [{"text": {"content": note.full_text}}]}}],
        }
        # timeout guards the single worker thread against a hung Notion socket
        # (SEC-3); a stuck delivery flips the job to error instead of blocking forever.
        resp = requests.post("https://api.notion.com/v1/pages", headers=headers, json=page, timeout=15)
        resp.raise_for_status()
        log.info(f"Notion page created: '{note.title}'")
