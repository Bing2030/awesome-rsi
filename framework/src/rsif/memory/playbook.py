"""Playbook: the ACE-style evolving context, backed by the MEMORY artifact.

The playbook is a structured list of sections (id, title, body). It evolves
only via *bounded* operations (add / update / delete, at most k items per
patch) - never wholesale rewrites - to avoid "context collapse" and keep the
edit surface disciplined.

Grounding: ACE [arXiv 2510.04618]; bounded edits [arXiv 2605.23904].
"""

from __future__ import annotations

import json
from dataclasses import dataclass


class PlaybookError(Exception):
    pass


@dataclass
class Section:
    id: str
    title: str
    body: str

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "body": self.body}

    @classmethod
    def from_dict(cls, d: dict) -> "Section":
        return cls(d["id"], d.get("title", ""), d.get("body", ""))


def parse_playbook(json_text: str) -> list[Section]:
    data = json.loads(json_text)
    return [Section.from_dict(item) for item in data]


def serialize_playbook(sections: list[Section]) -> str:
    return json.dumps([s.to_dict() for s in sections], indent=2)


class PlaybookEditor:
    """Validates and applies bounded edits to a playbook."""

    def __init__(self, max_sections: int = 12, max_ops_per_patch: int = 3):
        self.max_sections = max_sections
        self.max_ops_per_patch = max_ops_per_patch

    def check_bounded(self, ops: list[dict]) -> None:
        if len(ops) > self.max_ops_per_patch:
            raise PlaybookError(
                f"too many playbook ops ({len(ops)} > {self.max_ops_per_patch})")

    def apply(self, sections: list[Section], ops: list[dict]) -> list[Section]:
        """Apply add/update/delete ops. Returns the new section list.

        op schema: {"op": "add", "section": {...}} |
                   {"op": "update", "id": ..., "body": ...} |
                   {"op": "delete", "id": ...}
        """
        self.check_bounded(ops)
        by_id = {s.id: s for s in sections}
        order = [s.id for s in sections]

        for op in ops:
            kind = op["op"]
            if kind == "add":
                sec = Section.from_dict(op["section"])
                if sec.id in by_id:
                    raise PlaybookError(f"duplicate section id {sec.id!r}")
                if len(order) >= self.max_sections:
                    raise PlaybookError(
                        f"playbook full ({self.max_sections} sections)")
                by_id[sec.id] = sec
                order.append(sec.id)
            elif kind == "update":
                sid = op["id"]
                if sid not in by_id:
                    raise PlaybookError(f"unknown section {sid!r}")
                old = by_id[sid]
                by_id[sid] = Section(sid, old.title, op.get("body", old.body))
            elif kind == "delete":
                sid = op["id"]
                if sid not in by_id:
                    raise PlaybookError(f"unknown section {sid!r}")
                del by_id[sid]
                order.remove(sid)
            else:
                raise PlaybookError(f"unknown playbook op {kind!r}")

        return [by_id[sid] for sid in order]


def render(sections: list[Section]) -> str:
    return "\n\n".join(f"## {s.title}\n{s.body}" for s in sections)
