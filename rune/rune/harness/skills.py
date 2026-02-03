"""Skills system for Rune.

Implements a Codex-inspired skills mechanism where skills are markdown files
with YAML frontmatter that provide specialized instructions to the agent.

Skills follow a progressive disclosure approach:
1. Skills list always shown in system prompt (metadata only)
2. Full SKILL.md content loaded when explicitly mentioned
3. Referenced files loaded on-demand

Inspired by openai/codex codex-rs implementation.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import yaml


SKILL_FILENAME = "SKILL.md"
MAX_SCAN_DEPTH = 6


@dataclass(frozen=True)
class Skill:
    """A skill with its metadata and location."""

    name: str
    description: str
    path: Path
    short_description: str | None = None


@dataclass(frozen=True)
class SkillMention:
    """Represents explicit skill mentions in user input."""

    names: set[str]  # Plain mentions like $skill-name
    paths: set[str]  # Path mentions like [$skill](path/to/SKILL.md)


class SkillsManager:
    """Manages skill discovery, loading, and injection."""

    def __init__(self, working_dir: str | Path):
        self.working_dir = Path(working_dir).resolve()
        self._cache: list[Skill] | None = None

    # -------------------------------------------------------------------------
    # Discovery
    # -------------------------------------------------------------------------

    def discover_skills(self, force_reload: bool = False) -> list[Skill]:
        """Discover all available skills from configured roots.

        Args:
            force_reload: If True, bypass cache and rediscover

        Returns:
            List of discovered skills, sorted by name
        """
        if not force_reload and self._cache is not None:
            return list(self._cache)  # Return a copy

        skills: list[Skill] = []
        seen_paths: set[Path] = set()

        for root in self._get_skill_roots():
            if not root.exists() or not root.is_dir():
                continue

            for skill_path in self._scan_for_skills(root):
                # Skip if already seen (deduplication)
                if skill_path in seen_paths:
                    continue

                try:
                    skill = self._parse_skill(skill_path)
                    skills.append(skill)
                    seen_paths.add(skill_path)
                except Exception:
                    # Skip invalid skills
                    continue

        # Sort by name for stable ordering
        skills.sort(key=lambda s: (s.name.lower(), str(s.path)))

        self._cache = skills
        return list(skills)  # Return a copy

    def _get_skill_roots(self) -> list[Path]:
        """Get directories to scan for skills.

        Scans in order of precedence:
        1. <cwd>/.agents/skills (repo scope)
        2. <cwd>/.codex/skills (codex compat)
        3. <cwd>/skills (simple)
        4. ~/.agents/skills (user scope)
        5. $CODEX_HOME/skills (user scope, codex compat)

        Returns:
            List of paths to scan
        """
        roots = [
            self.working_dir / ".agents" / "skills",
            self.working_dir / ".codex" / "skills",
            self.working_dir / "skills",
        ]

        # User-level roots
        home = Path.home()
        roots.append(home / ".agents" / "skills")

        codex_home = os.getenv("CODEX_HOME")
        if codex_home:
            roots.append(Path(codex_home) / "skills")

        return roots

    def _scan_for_skills(self, root: Path) -> Iterator[Path]:
        """Recursively scan directory for SKILL.md files.

        Args:
            root: Directory to scan

        Yields:
            Paths to SKILL.md files
        """
        root = root.resolve()

        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden directories
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]

            # Check depth limit
            current = Path(dirpath)
            try:
                relative = current.relative_to(root)
                depth = len(relative.parts)
            except ValueError:
                depth = 0

            if depth > MAX_SCAN_DEPTH:
                dirnames[:] = []  # Don't recurse deeper
                continue

            # Yield SKILL.md if found
            if SKILL_FILENAME in filenames:
                yield (current / SKILL_FILENAME).resolve()

    def _parse_skill(self, path: Path) -> Skill:
        """Parse a SKILL.md file.

        Args:
            path: Path to SKILL.md

        Returns:
            Parsed Skill object

        Raises:
            ValueError: If skill is malformed
        """
        content = path.read_text(encoding="utf-8")

        # Extract frontmatter
        frontmatter = self._extract_frontmatter(content)
        if not frontmatter:
            raise ValueError(f"No frontmatter in {path}")

        # Parse YAML
        try:
            data = yaml.safe_load(frontmatter) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {path}: {e}")

        # Extract required fields
        name = str(data.get("name", "")).strip()
        description = str(data.get("description", "")).strip()

        if not name:
            raise ValueError(f"Missing 'name' in {path}")
        if not description:
            raise ValueError(f"Missing 'description' in {path}")

        # Validate constraints
        if len(name) > 64:
            raise ValueError(f"Name too long in {path}: {len(name)} > 64")
        if len(description) > 1024:
            raise ValueError(f"Description too long in {path}: {len(description)} > 1024")

        # Extract optional fields
        short_description = data.get("short_description")
        if short_description:
            short_description = str(short_description).strip()

        return Skill(
            name=name,
            description=description,
            path=path,
            short_description=short_description,
        )

    def _extract_frontmatter(self, content: str) -> str | None:
        """Extract YAML frontmatter from markdown content.

        Frontmatter format:
            ---
            name: skill-name
            description: skill description
            ---

            # Rest of markdown content

        Args:
            content: Full file content

        Returns:
            Frontmatter string or None if not found
        """
        lines = content.splitlines()

        if not lines or lines[0].strip() != "---":
            return None

        frontmatter_lines: list[str] = []
        for line in lines[1:]:
            if line.strip() == "---":
                # Found closing delimiter
                result = "\n".join(frontmatter_lines).strip()
                return result if result else None
            frontmatter_lines.append(line)

        # No closing delimiter found
        return None

    # -------------------------------------------------------------------------
    # Prompt rendering
    # -------------------------------------------------------------------------

    def render_skills_section(self) -> str | None:
        """Render skills section for system prompt.

        This shows available skills with their metadata, plus usage instructions.
        The full SKILL.md content is loaded separately when mentioned.

        Returns:
            Formatted markdown section or None if no skills
        """
        skills = self.discover_skills()
        if not skills:
            return None

        lines = [
            "## Skills",
            "",
            "Skills are local instruction bundles stored in `SKILL.md` files. "
            "Each skill provides specialized knowledge, workflows, or procedures for specific tasks.",
            "",
            "### Available Skills",
            "",
        ]

        for skill in skills:
            desc = skill.short_description or skill.description
            lines.append(f"- **{skill.name}**: {desc}")
            lines.append(f"  - Path: `{skill.path.as_posix()}`")

        lines.extend([
            "",
            "### How to Use Skills",
            "",
            "**Activation**: Skills are activated when:",
            "- User explicitly mentions a skill: `$skill-name` or `[$skill-name](path)`",
            "- Task clearly matches a skill's description",
            "",
            "**Progressive Disclosure**:",
            "1. When a skill is activated, read its SKILL.md file",
            "2. Follow the instructions and workflow in the skill",
            "3. Load referenced files (scripts, docs) only as needed",
            "4. Prefer running existing scripts over rewriting code",
            "",
            "**Best Practices**:",
            "- Only load what you need - respect the context budget",
            "- Skills are per-turn - don't persist across messages unless re-mentioned",
            "- If a skill can't be applied (missing files, unclear), explain and adapt",
            "",
        ])

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Mention detection and injection
    # -------------------------------------------------------------------------

    def extract_mentions(self, text: str) -> SkillMention:
        """Extract explicit skill mentions from user text.

        Supports two formats:
        - Plain: $skill-name
        - Linked: [$skill-name](path/to/SKILL.md)

        Args:
            text: User message text

        Returns:
            SkillMention with names and paths
        """
        names: set[str] = set()
        paths: set[str] = set()

        # Pattern for linked mentions: [$name](path)
        linked_pattern = re.compile(r'\[\$(?P<name>[A-Za-z0-9_-]+)\]\((?P<path>[^)]+)\)')
        for match in linked_pattern.finditer(text):
            name = match.group("name")
            path = match.group("path").strip()
            if name:
                names.add(name)
            if path:
                paths.add(path)

        # Pattern for plain mentions: $name
        plain_pattern = re.compile(r'\$(?P<name>[A-Za-z0-9_-]+)')
        for match in plain_pattern.finditer(text):
            name = match.group("name")
            if name:
                names.add(name)

        return SkillMention(names=names, paths=paths)

    def get_skills_for_mentions(self, mention: SkillMention) -> list[Skill]:
        """Resolve skill mentions to actual skills.

        Args:
            mention: Extracted mentions from user input

        Returns:
            List of resolved skills (deduplicated)
        """
        skills = self.discover_skills()
        by_name = {s.name: s for s in skills}

        selected: list[Skill] = []
        seen_paths: set[Path] = set()

        # Resolve by name
        for name in mention.names:
            if name in by_name:
                skill = by_name[name]
                if skill.path not in seen_paths:
                    selected.append(skill)
                    seen_paths.add(skill.path)

        # Resolve by path
        for path_str in mention.paths:
            path = Path(path_str)
            if not path.is_absolute():
                path = (self.working_dir / path).resolve()

            # Must be a SKILL.md file
            if path.name.lower() != SKILL_FILENAME.lower():
                continue

            # Find matching skill
            for skill in skills:
                if skill.path == path and skill.path not in seen_paths:
                    selected.append(skill)
                    seen_paths.add(skill.path)
                    break

        return selected

    def load_skill_content(self, skill: Skill) -> str | None:
        """Load full content of a skill file.

        Args:
            skill: Skill to load

        Returns:
            Full SKILL.md content or None on error
        """
        try:
            return skill.path.read_text(encoding="utf-8")
        except Exception:
            return None

    def apply_turn_injections(self, session: Any) -> None:
        """Inject mentioned skill content into the session for the current turn.

        This inspects the last user message for skill mentions and injects
        the full SKILL.md content as system messages.

        Args:
            session: Session object with messages attribute
        """
        # Import here to avoid circular dependency
        from rune.harness.session import Message

        # Remove previous skill injections
        session.messages = [
            m for m in session.messages
            if not (m.role == "system" and (m.content or "").startswith("[SKILL:"))
        ]

        # Find last user message
        last_user_msg = None
        for msg in reversed(session.messages):
            if msg.role == "user":
                last_user_msg = msg
                break

        if not last_user_msg or not last_user_msg.content:
            return

        # Extract mentions from user message
        mention = self.extract_mentions(last_user_msg.content)
        skills = self.get_skills_for_mentions(mention)

        if not skills:
            return

        # Load and inject skill content
        injections: list[Message] = []
        for skill in skills:
            content = self.load_skill_content(skill)
            if content:
                injections.append(
                    Message(
                        role="system",
                        content=f"[SKILL: {skill.name} @ {skill.path.as_posix()}]\n{content}\n[END SKILL]",
                    )
                )

        # Insert after first system message (if present), else at start
        if injections:
            insert_at = 1 if session.messages and session.messages[0].role == "system" else 0
            session.messages[insert_at:insert_at] = injections
