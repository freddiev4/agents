"""Skills harness.

Implements a Codex-like "skills" mechanism for Rune.

A *skill* is a local instruction bundle stored in a `SKILL.md` file.

This harness provides two integrations:

1) System prompt augmentation: render a "Skills" section listing available skills
   and how to use them.
2) Per-turn injection: when the user explicitly mentions a skill (e.g. `$my-skill`
   or `[$my-skill](path/to/SKILL.md)`), inject the full SKILL.md contents into the
   prompt for that turn.

Design goals:
- Keep this logic isolated to the harness layer.
- Do not persist injected skill bodies across turns.
- Be conservative: only inject on explicit mention (for now).

This is inspired by openai/codex codex-rs implementation.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rune.harness.session import Message, Session


SKILL_FILENAME = "SKILL.md"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path


class SkillsHarness:
    def __init__(self, working_dir: str, *, max_scan_depth: int = 6):
        self.working_dir = Path(working_dir)
        self.max_scan_depth = max_scan_depth
        self._skills_cache: list[Skill] | None = None

    # ---------------------------------------------------------------------
    # Discovery
    # ---------------------------------------------------------------------

    def _skill_roots(self) -> list[Path]:
        """Return directories to scan for skills.

        Current roots (simple, repo-local):
        - <cwd>/.agents/skills
        - <cwd>/.codex/skills
        - <cwd>/skills

        This can be extended later to include user/global roots.
        """

        cwd = self.working_dir
        return [cwd / ".agents" / "skills", cwd / ".codex" / "skills", cwd / "skills"]

    def _discover_skills(self) -> list[Skill]:
        skills: list[Skill] = []
        seen_paths: set[Path] = set()

        for root in self._skill_roots():
            if not root.exists() or not root.is_dir():
                continue

            for skill_path in self._walk_for_skill_files(root):
                try:
                    skill = self._parse_skill_file(skill_path)
                except Exception:
                    continue

                if skill.path in seen_paths:
                    continue
                seen_paths.add(skill.path)
                skills.append(skill)

        # stable ordering
        skills.sort(key=lambda s: (s.name.lower(), str(s.path)))
        return skills

    def _walk_for_skill_files(self, root: Path) -> Iterable[Path]:
        root = root.resolve()
        for dirpath, dirnames, filenames in os.walk(root):
            # prune hidden dirs
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]

            current = Path(dirpath)
            try:
                rel = current.relative_to(root)
                depth = len(rel.parts)
            except Exception:
                depth = 0
            if depth > self.max_scan_depth:
                dirnames[:] = []
                continue

            if SKILL_FILENAME in filenames:
                yield (current / SKILL_FILENAME).resolve()

    def _parse_skill_file(self, path: Path) -> Skill:
        text = path.read_text(encoding="utf-8")
        fm = _extract_frontmatter(text)
        if fm is None:
            raise ValueError("missing frontmatter")
        data = yaml.safe_load(fm) or {}
        name = str(data.get("name", "")).strip()
        description = str(data.get("description", "")).strip()
        if not name or not description:
            raise ValueError("missing name/description")
        return Skill(name=name, description=description, path=path)

    def skills(self, *, force_reload: bool = False) -> list[Skill]:
        if force_reload or self._skills_cache is None:
            self._skills_cache = self._discover_skills()
        return list(self._skills_cache)

    # ---------------------------------------------------------------------
    # Prompt rendering
    # ---------------------------------------------------------------------

    def render_skills_section(self) -> str | None:
        skills = self.skills()
        if not skills:
            return None

        lines: list[str] = []
        lines.append("## Skills")
        lines.append(
            "A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. "
            "Below is the list of skills that can be used. Each entry includes a name, description, "
            "and file path so you can open the source for full instructions when using a specific skill."
        )
        lines.append("### Available skills")
        for s in skills:
            lines.append(f"- {s.name}: {s.description} (file: {s.path.as_posix()})")

        lines.append("### How to use skills")
        lines.append(
            "- Trigger rules: If the user names a skill (with `$SkillName` or plain text) OR the task clearly "
            "matches a skill's description shown above, you must use that skill for that turn. Multiple mentions "
            "mean use them all. Do not carry skills across turns unless re-mentioned.\n"
            "- How to use a skill (progressive disclosure):\n"
            "  1) After deciding to use a skill, open its `SKILL.md`. Read only enough to follow the workflow.\n"
            "  2) When `SKILL.md` references relative paths, resolve them relative to the skill directory first.\n"
            "  3) Load only the specific files needed; don't bulk-load everything.\n"
            "  4) Prefer running or patching referenced scripts instead of retyping large code blocks.\n"
            "- Safety and fallback: If a skill can't be applied cleanly (missing files, unclear instructions), "
            "state the issue, pick the next-best approach, and continue."
        )

        return "\n".join(lines)

    # ---------------------------------------------------------------------
    # Per-turn injection
    # ---------------------------------------------------------------------

    def apply_turn_injections(self, session: Session) -> None:
        """Inject mentioned skill bodies into the session for the next model call.

        This mutates `session.messages` by inserting temporary system messages.
        Any previously injected skill messages are removed first.
        """

        # Remove previous injections
        session.messages = [
            m
            for m in session.messages
            if not (m.role == "system" and (m.content or "").startswith("[SKILL:"))
        ]

        last_user = next((m for m in reversed(session.messages) if m.role == "user"), None)
        if not last_user or not last_user.content:
            return

        mentioned = self._collect_explicit_mentions(last_user.content)
        if not mentioned:
            return

        skills = self.skills()
        by_name = {s.name: s for s in skills}
        selected: list[Skill] = []

        for name in mentioned.names:
            if name in by_name:
                selected.append(by_name[name])

        for p in mentioned.paths:
            sp = Path(p)
            if not sp.is_absolute():
                sp = (self.working_dir / sp).resolve()
            if sp.name.lower() != SKILL_FILENAME.lower():
                continue
            for s in skills:
                if s.path == sp:
                    selected.append(s)
                    break

        # dedupe by path
        seen: set[Path] = set()
        selected = [s for s in selected if not (s.path in seen or seen.add(s.path))]
        if not selected:
            return

        # Insert after the first system message (if present), else at start.
        insert_at = 1 if session.messages and session.messages[0].role == "system" else 0
        injections: list[Message] = []
        for s in selected:
            try:
                contents = s.path.read_text(encoding="utf-8")
            except Exception:
                continue
            injections.append(
                Message(
                    role="system",
                    content=f"[SKILL:{s.name} @ {s.path.as_posix()}]\n{contents}\n[END SKILL]",
                )
            )

        if injections:
            session.messages[insert_at:insert_at] = injections

    def _collect_explicit_mentions(self, text: str) -> "ToolMentions":
        return extract_tool_mentions(text)


@dataclass(frozen=True)
class ToolMentions:
    names: set[str]
    paths: set[str]


_LINKED = re.compile(r"\[\$(?P<name>[A-Za-z0-9_-]+)\]\((?P<path>[^)]+)\)")
_PLAIN = re.compile(r"\$(?P<name>[A-Za-z0-9_-]+)")


def extract_tool_mentions(text: str) -> ToolMentions:
    names: set[str] = set()
    paths: set[str] = set()

    for m in _LINKED.finditer(text):
        name = m.group("name")
        path = m.group("path").strip()
        if name:
            names.add(name)
        if path:
            paths.add(path)

    for m in _PLAIN.finditer(text):
        name = m.group("name")
        if name:
            names.add(name)

    return ToolMentions(names=names, paths=paths)


def _extract_frontmatter(contents: str) -> str | None:
    lines = contents.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    out: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return "\n".join(out).strip() or None
        out.append(line)
    return None
