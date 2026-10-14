"""
Resident / staff directory.

Source of truth for which staff member is responsible for each resident:
  - GitHub Actions: the LMC_RESIDENTS_JSON secret
  - Local:          residents.json next to this file

Each entry: {"id": "...", "name": "...", "staff_name": "...", "staff_email": "..."}

Staff email addresses are only ever read by the backend (server.py). They are
never written to data.json or sent to the browser.
"""

import json
import os
import re

RESIDENTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "residents.json")


def load_residents() -> list[dict]:
    """Resident list from the LMC_RESIDENTS_JSON env var (GitHub secret) or the local residents.json."""
    raw = os.getenv("LMC_RESIDENTS_JSON", "").strip()
    if raw:
        data = json.loads(raw)
    else:
        with open(RESIDENTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    return [r for r in data if r.get("id") and r.get("name")]


def normalize_name(name: str) -> str:
    """'Molly  (Kaydan) Searson' -> 'molly kaydan searson' (case, spacing and punctuation ignored)."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", (name or "").lower())).strip()


class StaffDirectory:
    """Look up the responsible staff member for a resident by LMC id or by name."""

    def __init__(self, residents: list[dict]):
        self._by_id = {r["id"]: r for r in residents}
        self._by_name = {normalize_name(r["name"]): r for r in residents}
        # Fallback key: first + last word, so "Molly Searson" still matches "Molly (Kaydan) Searson"
        self._by_short = {}
        for r in residents:
            words = normalize_name(r["name"]).split()
            if len(words) >= 2:
                self._by_short.setdefault(f"{words[0]} {words[-1]}", r)

    @classmethod
    def load(cls) -> "StaffDirectory":
        try:
            return cls(load_residents())
        except Exception as e:
            print(f"[Directory] WARNING: resident list unavailable ({e}); staff names will be blank.")
            return cls([])

    def find(self, resident_name: str = "", resident_id: str = "") -> dict | None:
        if resident_id and resident_id in self._by_id:
            return self._by_id[resident_id]
        key = normalize_name(resident_name)
        if key in self._by_name:
            return self._by_name[key]
        words = key.split()
        if len(words) >= 2:
            return self._by_short.get(f"{words[0]} {words[-1]}")
        return None

    def staff_name(self, resident_name: str = "", resident_id: str = "") -> str:
        entry = self.find(resident_name, resident_id)
        return (entry or {}).get("staff_name", "")

    def attach_staff_names(self, data: dict) -> dict:
        """Set item["staff_name"] on every dashboard item (in place). Never adds email addresses."""
        for section in DATA_SECTIONS:
            for item in data.get(section) or []:
                item_id = str(item.get("id", ""))
                resident_id = item_id[3:] if item_id.startswith("fp-") else ""
                item["staff_name"] = self.staff_name(item.get("resident", ""), resident_id)
                item.pop("staff_email", None)
        return data


DATA_SECTIONS = ("incidents_needs_review", "incidents_open", "support_plans_overdue", "goals_overdue", "future_plans_overdue")
