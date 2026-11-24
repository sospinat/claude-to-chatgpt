"""Rebuild the two release ZIPs from the translator's source tree."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/claude-to-chatgpt"
SKILL = "translate-claude-package"
sys.path.insert(0, str(PLUGIN / "skills" / SKILL / "scripts"))

from translate import archive_bytes, read_package


def main():
    output = ROOT / "downloads"
    output.mkdir(exist_ok=True)
    files, _ = read_package(PLUGIN)
    license_text = (ROOT / "LICENSE").read_bytes()
    files["LICENSE"] = license_text
    (output / "claude-to-chatgpt.zip").write_bytes(archive_bytes(files))
    prefix = f"skills/{SKILL}/"
    skill = {f"{SKILL}/{k[len(prefix):]}": v for k, v in files.items() if k.startswith(prefix)}
    skill[f"{SKILL}/LICENSE"] = license_text
    (output / f"{SKILL}.zip").write_bytes(archive_bytes(skill))


if __name__ == "__main__":
    main()
