from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
VALIDATOR = Path.home() / ".codex/skills/.system/skill-creator/scripts/quick_validate.py"


def test_photo_center_skill_is_valid_and_discoverable() -> None:
    skill = ROOT / "skills/icloud-photo-center"
    result = subprocess.run(
        ["python3", str(VALIDATOR), str(skill)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (skill / "agents/openai.yaml").exists()
    assert "icloud-photo-sync status --scope photo --format json" in (skill / "SKILL.md").read_text()
