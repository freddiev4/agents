"""Tests for the skills system."""

import pytest
from pathlib import Path
from rune.harness.skills import (
    SkillsManager,
    Skill,
    SkillMention,
    SKILL_FILENAME,
)


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace with skills."""
    # Create skill directories
    agents_skills = tmp_path / ".agents" / "skills"
    agents_skills.mkdir(parents=True)

    codex_skills = tmp_path / ".codex" / "skills"
    codex_skills.mkdir(parents=True)

    simple_skills = tmp_path / "skills"
    simple_skills.mkdir(parents=True)

    return tmp_path


@pytest.fixture
def sample_skill_content():
    """Sample SKILL.md content."""
    return """---
name: test-skill
description: A test skill for testing purposes
short_description: Test skill
---

# Test Skill

This is a test skill with some instructions.

## Usage

1. Do something
2. Do something else
"""


@pytest.fixture
def invalid_skill_no_frontmatter():
    """Skill without frontmatter."""
    return """# Invalid Skill

This skill has no frontmatter.
"""


@pytest.fixture
def invalid_skill_missing_name():
    """Skill with missing name."""
    return """---
description: A skill without a name
---

# Invalid Skill
"""


@pytest.fixture
def invalid_skill_missing_description():
    """Skill with missing description."""
    return """---
name: invalid-skill
---

# Invalid Skill
"""


class TestSkillsManager:
    """Tests for SkillsManager class."""

    def test_init(self, temp_workspace):
        """Test SkillsManager initialization."""
        manager = SkillsManager(temp_workspace)
        assert manager.working_dir == temp_workspace.resolve()
        assert manager._cache is None

    def test_get_skill_roots(self, temp_workspace):
        """Test skill root discovery."""
        manager = SkillsManager(temp_workspace)
        roots = manager._get_skill_roots()

        # Should have at least these roots
        assert temp_workspace / ".agents" / "skills" in roots
        assert temp_workspace / ".codex" / "skills" in roots
        assert temp_workspace / "skills" in roots
        assert Path.home() / ".agents" / "skills" in roots

    def test_discover_no_skills(self, temp_workspace):
        """Test discovery when no skills exist."""
        manager = SkillsManager(temp_workspace)
        skills = manager.discover_skills()
        assert skills == []

    def test_discover_single_skill(self, temp_workspace, sample_skill_content):
        """Test discovering a single skill."""
        # Create a skill
        skill_dir = temp_workspace / ".agents" / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / SKILL_FILENAME).write_text(sample_skill_content)

        manager = SkillsManager(temp_workspace)
        skills = manager.discover_skills()

        assert len(skills) == 1
        assert skills[0].name == "test-skill"
        assert skills[0].description == "A test skill for testing purposes"
        assert skills[0].short_description == "Test skill"
        assert skills[0].path == skill_dir / SKILL_FILENAME

    def test_discover_multiple_skills(self, temp_workspace):
        """Test discovering multiple skills from different roots."""
        # Create skills in different locations
        skill1_dir = temp_workspace / ".agents" / "skills" / "skill-one"
        skill1_dir.mkdir(parents=True)
        (skill1_dir / SKILL_FILENAME).write_text("""---
name: skill-one
description: First test skill
---
# Skill One
""")

        skill2_dir = temp_workspace / ".codex" / "skills" / "skill-two"
        skill2_dir.mkdir(parents=True)
        (skill2_dir / SKILL_FILENAME).write_text("""---
name: skill-two
description: Second test skill
---
# Skill Two
""")

        manager = SkillsManager(temp_workspace)
        skills = manager.discover_skills()

        assert len(skills) == 2
        skill_names = {s.name for s in skills}
        assert skill_names == {"skill-one", "skill-two"}

    def test_discover_nested_skills(self, temp_workspace):
        """Test discovering skills in nested directories."""
        # Create nested skill
        nested_dir = temp_workspace / ".agents" / "skills" / "category" / "nested-skill"
        nested_dir.mkdir(parents=True)
        (nested_dir / SKILL_FILENAME).write_text("""---
name: nested-skill
description: A nested skill
---
# Nested
""")

        manager = SkillsManager(temp_workspace)
        skills = manager.discover_skills()

        assert len(skills) == 1
        assert skills[0].name == "nested-skill"

    def test_discover_caching(self, temp_workspace, sample_skill_content):
        """Test that discovery results are cached."""
        skill_dir = temp_workspace / ".agents" / "skills" / "test"
        skill_dir.mkdir(parents=True)
        (skill_dir / SKILL_FILENAME).write_text(sample_skill_content)

        manager = SkillsManager(temp_workspace)

        # First call should populate cache
        skills1 = manager.discover_skills()
        assert manager._cache is not None
        cache_ref = manager._cache

        # Second call should use cache (but return a copy)
        skills2 = manager.discover_skills()
        assert manager._cache is cache_ref  # Cache unchanged
        assert skills1 is not skills2  # Returns copies
        assert skills1 == skills2  # But content is the same

    def test_discover_force_reload(self, temp_workspace, sample_skill_content):
        """Test force reload bypasses cache."""
        skill_dir = temp_workspace / ".agents" / "skills" / "test"
        skill_dir.mkdir(parents=True)
        (skill_dir / SKILL_FILENAME).write_text(sample_skill_content)

        manager = SkillsManager(temp_workspace)

        # First discovery
        skills1 = manager.discover_skills()
        first_cache = manager._cache

        # Force reload should invalidate cache
        skills2 = manager.discover_skills(force_reload=True)
        assert manager._cache is not first_cache

    def test_skip_hidden_directories(self, temp_workspace):
        """Test that hidden directories are skipped."""
        # Create skill in hidden directory
        hidden_dir = temp_workspace / ".agents" / "skills" / ".hidden" / "skill"
        hidden_dir.mkdir(parents=True)
        (hidden_dir / SKILL_FILENAME).write_text("""---
name: hidden-skill
description: Should not be found
---
""")

        manager = SkillsManager(temp_workspace)
        skills = manager.discover_skills()

        # Should not find the hidden skill
        assert len(skills) == 0

    def test_max_depth_limit(self, temp_workspace):
        """Test that depth limit is respected."""
        # Create very deeply nested skill (beyond limit)
        deep_path = temp_workspace / ".agents" / "skills"
        for i in range(8):  # Beyond MAX_SCAN_DEPTH
            deep_path = deep_path / f"level{i}"
        deep_path.mkdir(parents=True)
        (deep_path / SKILL_FILENAME).write_text("""---
name: deep-skill
description: Too deep
---
""")

        manager = SkillsManager(temp_workspace)
        skills = manager.discover_skills()

        # Should not find the deeply nested skill
        assert len(skills) == 0

    def test_skip_invalid_skills(self, temp_workspace, invalid_skill_no_frontmatter):
        """Test that invalid skills are skipped."""
        # Create valid and invalid skills
        valid_dir = temp_workspace / ".agents" / "skills" / "valid"
        valid_dir.mkdir(parents=True)
        (valid_dir / SKILL_FILENAME).write_text("""---
name: valid-skill
description: Valid skill
---
""")

        invalid_dir = temp_workspace / ".agents" / "skills" / "invalid"
        invalid_dir.mkdir(parents=True)
        (invalid_dir / SKILL_FILENAME).write_text(invalid_skill_no_frontmatter)

        manager = SkillsManager(temp_workspace)
        skills = manager.discover_skills()

        # Should only find the valid skill
        assert len(skills) == 1
        assert skills[0].name == "valid-skill"

    def test_deduplication(self, temp_workspace):
        """Test that duplicate paths are deduplicated."""
        # Create skill that could be found multiple times
        skill_dir = temp_workspace / ".agents" / "skills" / "dupe"
        skill_dir.mkdir(parents=True)
        (skill_dir / SKILL_FILENAME).write_text("""---
name: dupe-skill
description: Duplicate skill
---
""")

        manager = SkillsManager(temp_workspace)
        skills = manager.discover_skills()

        # Should only appear once
        assert len(skills) == 1
        assert skills[0].name == "dupe-skill"


class TestSkillParsing:
    """Tests for skill file parsing."""

    def test_parse_valid_skill(self, temp_workspace):
        """Test parsing a valid skill."""
        skill_content = """---
name: test-skill
description: A test skill
short_description: Test
---

# Test Skill
"""
        skill_path = temp_workspace / SKILL_FILENAME
        skill_path.write_text(skill_content)

        manager = SkillsManager(temp_workspace)
        skill = manager._parse_skill(skill_path)

        assert skill.name == "test-skill"
        assert skill.description == "A test skill"
        assert skill.short_description == "Test"
        assert skill.path == skill_path

    def test_parse_skill_without_short_description(self, temp_workspace):
        """Test parsing skill without short_description."""
        skill_content = """---
name: test-skill
description: A test skill
---
"""
        skill_path = temp_workspace / SKILL_FILENAME
        skill_path.write_text(skill_content)

        manager = SkillsManager(temp_workspace)
        skill = manager._parse_skill(skill_path)

        assert skill.name == "test-skill"
        assert skill.short_description is None

    def test_parse_skill_no_frontmatter(self, temp_workspace, invalid_skill_no_frontmatter):
        """Test parsing skill without frontmatter."""
        skill_path = temp_workspace / SKILL_FILENAME
        skill_path.write_text(invalid_skill_no_frontmatter)

        manager = SkillsManager(temp_workspace)

        with pytest.raises(ValueError, match="No frontmatter"):
            manager._parse_skill(skill_path)

    def test_parse_skill_missing_name(self, temp_workspace, invalid_skill_missing_name):
        """Test parsing skill with missing name."""
        skill_path = temp_workspace / SKILL_FILENAME
        skill_path.write_text(invalid_skill_missing_name)

        manager = SkillsManager(temp_workspace)

        with pytest.raises(ValueError, match="Missing 'name'"):
            manager._parse_skill(skill_path)

    def test_parse_skill_missing_description(self, temp_workspace, invalid_skill_missing_description):
        """Test parsing skill with missing description."""
        skill_path = temp_workspace / SKILL_FILENAME
        skill_path.write_text(invalid_skill_missing_description)

        manager = SkillsManager(temp_workspace)

        with pytest.raises(ValueError, match="Missing 'description'"):
            manager._parse_skill(skill_path)

    def test_parse_skill_name_too_long(self, temp_workspace):
        """Test parsing skill with name exceeding limit."""
        long_name = "a" * 65
        skill_content = f"""---
name: {long_name}
description: Test
---
"""
        skill_path = temp_workspace / SKILL_FILENAME
        skill_path.write_text(skill_content)

        manager = SkillsManager(temp_workspace)

        with pytest.raises(ValueError, match="Name too long"):
            manager._parse_skill(skill_path)

    def test_parse_skill_description_too_long(self, temp_workspace):
        """Test parsing skill with description exceeding limit."""
        long_desc = "a" * 1025
        skill_content = f"""---
name: test
description: {long_desc}
---
"""
        skill_path = temp_workspace / SKILL_FILENAME
        skill_path.write_text(skill_content)

        manager = SkillsManager(temp_workspace)

        with pytest.raises(ValueError, match="Description too long"):
            manager._parse_skill(skill_path)

    def test_parse_skill_invalid_yaml(self, temp_workspace):
        """Test parsing skill with invalid YAML."""
        skill_content = """---
name: test
description: [invalid: yaml: syntax
---
"""
        skill_path = temp_workspace / SKILL_FILENAME
        skill_path.write_text(skill_content)

        manager = SkillsManager(temp_workspace)

        with pytest.raises(ValueError, match="Invalid YAML"):
            manager._parse_skill(skill_path)


class TestFrontmatterExtraction:
    """Tests for frontmatter extraction."""

    def test_extract_valid_frontmatter(self, temp_workspace):
        """Test extracting valid frontmatter."""
        content = """---
name: test
description: test skill
---

# Content
"""
        manager = SkillsManager(temp_workspace)
        fm = manager._extract_frontmatter(content)

        assert fm is not None
        assert "name: test" in fm
        assert "description: test skill" in fm

    def test_extract_no_frontmatter(self, temp_workspace):
        """Test extracting from content without frontmatter."""
        content = "# No frontmatter here"
        manager = SkillsManager(temp_workspace)
        fm = manager._extract_frontmatter(content)

        assert fm is None

    def test_extract_missing_closing_delimiter(self, temp_workspace):
        """Test extracting frontmatter without closing delimiter."""
        content = """---
name: test
description: test skill

# Content (no closing ---)
"""
        manager = SkillsManager(temp_workspace)
        fm = manager._extract_frontmatter(content)

        assert fm is None

    def test_extract_empty_frontmatter(self, temp_workspace):
        """Test extracting empty frontmatter."""
        content = """---
---

# Content
"""
        manager = SkillsManager(temp_workspace)
        fm = manager._extract_frontmatter(content)

        assert fm is None  # Empty frontmatter returns None


class TestMentionExtraction:
    """Tests for skill mention extraction."""

    def test_extract_plain_mention(self, temp_workspace):
        """Test extracting plain skill mention."""
        manager = SkillsManager(temp_workspace)
        mention = manager.extract_mentions("Please use $test-skill for this task")

        assert "test-skill" in mention.names
        assert len(mention.paths) == 0

    def test_extract_multiple_plain_mentions(self, temp_workspace):
        """Test extracting multiple plain mentions."""
        manager = SkillsManager(temp_workspace)
        mention = manager.extract_mentions("Use $skill-one and $skill-two")

        assert "skill-one" in mention.names
        assert "skill-two" in mention.names

    def test_extract_linked_mention(self, temp_workspace):
        """Test extracting linked skill mention."""
        manager = SkillsManager(temp_workspace)
        mention = manager.extract_mentions("Use [$test-skill](path/to/SKILL.md)")

        assert "test-skill" in mention.names
        assert "path/to/SKILL.md" in mention.paths

    def test_extract_mixed_mentions(self, temp_workspace):
        """Test extracting both plain and linked mentions."""
        manager = SkillsManager(temp_workspace)
        text = "Use $plain-skill and [$linked-skill](path/to/SKILL.md)"
        mention = manager.extract_mentions(text)

        assert "plain-skill" in mention.names
        assert "linked-skill" in mention.names
        assert "path/to/SKILL.md" in mention.paths

    def test_extract_no_mentions(self, temp_workspace):
        """Test text without skill mentions."""
        manager = SkillsManager(temp_workspace)
        mention = manager.extract_mentions("Just regular text here")

        assert len(mention.names) == 0
        assert len(mention.paths) == 0

    def test_extract_with_underscores(self, temp_workspace):
        """Test skill names with underscores."""
        manager = SkillsManager(temp_workspace)
        mention = manager.extract_mentions("Use $skill_name")

        assert "skill_name" in mention.names

    def test_extract_with_numbers(self, temp_workspace):
        """Test skill names with numbers."""
        manager = SkillsManager(temp_workspace)
        mention = manager.extract_mentions("Use $skill123")

        assert "skill123" in mention.names


class TestSkillResolution:
    """Tests for resolving mentions to actual skills."""

    def test_resolve_by_name(self, temp_workspace):
        """Test resolving skill by name."""
        # Create a skill
        skill_dir = temp_workspace / ".agents" / "skills" / "test"
        skill_dir.mkdir(parents=True)
        (skill_dir / SKILL_FILENAME).write_text("""---
name: test-skill
description: Test skill
---
""")

        manager = SkillsManager(temp_workspace)
        mention = SkillMention(names={"test-skill"}, paths=set())
        skills = manager.get_skills_for_mentions(mention)

        assert len(skills) == 1
        assert skills[0].name == "test-skill"

    def test_resolve_by_path(self, temp_workspace):
        """Test resolving skill by path."""
        # Create a skill
        skill_dir = temp_workspace / ".agents" / "skills" / "test"
        skill_dir.mkdir(parents=True)
        skill_path = skill_dir / SKILL_FILENAME
        skill_path.write_text("""---
name: test-skill
description: Test skill
---
""")

        manager = SkillsManager(temp_workspace)
        relative_path = ".agents/skills/test/SKILL.md"
        mention = SkillMention(names=set(), paths={relative_path})
        skills = manager.get_skills_for_mentions(mention)

        assert len(skills) == 1
        assert skills[0].name == "test-skill"

    def test_resolve_nonexistent_skill(self, temp_workspace):
        """Test resolving nonexistent skill."""
        manager = SkillsManager(temp_workspace)
        mention = SkillMention(names={"nonexistent"}, paths=set())
        skills = manager.get_skills_for_mentions(mention)

        assert len(skills) == 0

    def test_resolve_deduplication(self, temp_workspace):
        """Test that same skill mentioned multiple ways is deduplicated."""
        # Create a skill
        skill_dir = temp_workspace / ".agents" / "skills" / "test"
        skill_dir.mkdir(parents=True)
        skill_path = skill_dir / SKILL_FILENAME
        skill_path.write_text("""---
name: test-skill
description: Test skill
---
""")

        manager = SkillsManager(temp_workspace)
        # Mention same skill by both name and path
        mention = SkillMention(
            names={"test-skill"},
            paths={".agents/skills/test/SKILL.md"}
        )
        skills = manager.get_skills_for_mentions(mention)

        # Should only return once
        assert len(skills) == 1


class TestSkillsRendering:
    """Tests for rendering skills section."""

    def test_render_no_skills(self, temp_workspace):
        """Test rendering when no skills exist."""
        manager = SkillsManager(temp_workspace)
        section = manager.render_skills_section()

        assert section is None

    def test_render_single_skill(self, temp_workspace):
        """Test rendering with a single skill."""
        skill_dir = temp_workspace / ".agents" / "skills" / "test"
        skill_dir.mkdir(parents=True)
        (skill_dir / SKILL_FILENAME).write_text("""---
name: test-skill
description: A test skill for testing
short_description: Test skill
---
""")

        manager = SkillsManager(temp_workspace)
        section = manager.render_skills_section()

        assert section is not None
        assert "## Skills" in section
        assert "test-skill" in section
        assert "Test skill" in section  # Uses short_description
        assert "Available Skills" in section
        assert "How to Use Skills" in section

    def test_render_multiple_skills(self, temp_workspace):
        """Test rendering with multiple skills."""
        # Create two skills
        for i in range(2):
            skill_dir = temp_workspace / ".agents" / "skills" / f"skill{i}"
            skill_dir.mkdir(parents=True)
            (skill_dir / SKILL_FILENAME).write_text(f"""---
name: skill-{i}
description: Test skill {i}
---
""")

        manager = SkillsManager(temp_workspace)
        section = manager.render_skills_section()

        assert "skill-0" in section
        assert "skill-1" in section

    def test_render_uses_short_description(self, temp_workspace):
        """Test that rendering prefers short_description."""
        skill_dir = temp_workspace / ".agents" / "skills" / "test"
        skill_dir.mkdir(parents=True)
        (skill_dir / SKILL_FILENAME).write_text("""---
name: test-skill
description: This is a very long description that should not be shown
short_description: Short version
---
""")

        manager = SkillsManager(temp_workspace)
        section = manager.render_skills_section()

        assert "Short version" in section
        assert "very long description" not in section


class TestSkillContentLoading:
    """Tests for loading skill content."""

    def test_load_valid_skill(self, temp_workspace, sample_skill_content):
        """Test loading content from a valid skill."""
        skill_dir = temp_workspace / ".agents" / "skills" / "test"
        skill_dir.mkdir(parents=True)
        skill_path = skill_dir / SKILL_FILENAME
        skill_path.write_text(sample_skill_content)

        manager = SkillsManager(temp_workspace)
        skills = manager.discover_skills()
        content = manager.load_skill_content(skills[0])

        assert content == sample_skill_content

    def test_load_nonexistent_skill(self, temp_workspace):
        """Test loading content from nonexistent skill."""
        skill = Skill(
            name="fake",
            description="fake",
            path=temp_workspace / "nonexistent" / SKILL_FILENAME
        )

        manager = SkillsManager(temp_workspace)
        content = manager.load_skill_content(skill)

        assert content is None
