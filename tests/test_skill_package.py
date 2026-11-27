from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def test_photo_center_skill_is_valid_and_discoverable() -> None:
    skill = ROOT / "skills/photo-steward"
    skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert skill_text.startswith("---\n")
    frontmatter, separator, body = skill_text[4:].partition("\n---\n")
    assert separator
    metadata = yaml.safe_load(frontmatter)
    assert isinstance(metadata, dict)
    assert set(metadata) <= {"name", "description", "license", "allowed-tools", "metadata"}
    assert metadata["name"] == "photo-steward"
    description = metadata["description"]
    assert isinstance(description, str)
    assert 0 < len(description.strip()) <= 1024
    assert "<" not in description and ">" not in description
    assert not description.strip().startswith("[TODO:")
    assert (skill / "agents/openai.yaml").is_file()
    assert "photo-steward status --scope photo --format json" in body
    assert "icloud-photo-center" not in skill_text
