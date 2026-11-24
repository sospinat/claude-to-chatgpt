import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

import yaml

SCRIPT = (Path(__file__).resolve().parents[1] / "plugins/claude-to-chatgpt/skills"
          / "translate-claude-package/scripts/translate.py")


class TranslationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.source = self.work / "example"
        self.source.mkdir()
        self.dest = self.work / "converted"

    def put(self, name, contents):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def manifest(self, **fields):
        self.put(".claude-plugin/plugin.json", json.dumps({"name": "example", **fields}))

    def run_cli(self, source=None, ok=True):
        run = subprocess.run([sys.executable, str(SCRIPT), str(source or self.source),
                              "--out", str(self.dest)], capture_output=True, text=True)
        if ok:
            self.assertEqual(run.returncode, 0, run.stderr)
        else:
            self.assertNotEqual(run.returncode, 0)
        return run

    def report(self):
        return json.loads((self.dest / "migration.json").read_text(encoding="utf-8"))

    def test_single_skill_assets_explicit_only_and_folded_yaml(self):
        self.put("SKILL.md", "---\nname: Word Counter\ndescription: >-\n  Count words\n  on request.\ndisable-model-invocation: true\n---\nUse scripts/count.py on $ARGUMENTS")
        self.put("scripts/count.py", "raise RuntimeError('source code must never run')")
        self.put("LICENSE.txt", "Example license")
        self.put(".env", "FAKE_SECRET=EXAMPLE")
        self.run_cli(self.source / "SKILL.md")
        with ZipFile(self.dest / "skills/word-counter.zip") as z:
            body = z.read("word-counter/SKILL.md").decode()
            self.assertIn("Count words on request.", body)
            self.assertIn("arguments provided by the user", body)
            self.assertIn("word-counter/scripts/count.py", z.namelist())
            self.assertIn("word-counter/LICENSE.txt", z.namelist())
            self.assertNotIn("word-counter/.env", z.namelist())
            self.assertFalse(yaml.safe_load(z.read("word-counter/agents/openai.yaml"))["policy"]["allow_implicit_invocation"])

    def test_plugin_zip_maps_components_and_shared_files(self):
        self.manifest(version="2.0.1", commands=["./custom"], skills=["./extra"], hooks="./hooks.json")
        self.put("skills/summarize/SKILL.md", "Summarize the brief.")
        self.put("extra/helper/SKILL.md", "Use \x24{CLAUDE_PLUGIN_ROOT}/assets/template.txt")
        self.put("assets/template.txt", "Summary")
        self.put("agents/editor.md", "Edit the text.")
        self.put("custom/count.md", "Count $ARGUMENTS[0].")
        self.put("commands/ignored.md", "Superseded command.")
        self.put("hooks.json", "{}")
        self.put("NOTICE", "Example attribution")
        src = self.work / "plugin.zip"
        with ZipFile(src, "w") as z:
            for path in self.source.rglob("*"):
                if path.is_file():
                    z.write(path, "example-main/" + path.relative_to(self.source).as_posix())
        self.run_cli(src)
        with ZipFile(self.dest / "plugin.zip") as z:
            self.assertEqual(json.loads(z.read("plugin.json"))["version"], "2.0.1")
            self.assertIn("skills/helper/plugin-resources/assets/template.txt", z.namelist())
            self.assertIn("plugin-resources/assets/template.txt", z.read("skills/helper/SKILL.md").decode())
            self.assertIn("argument 1", z.read("skills/count/SKILL.md").decode())
            self.assertIn("skills/summarize/NOTICE", z.namelist())
            self.assertIn("skills/editor/SKILL.md", z.namelist())
            self.assertNotIn("skills/ignored/SKILL.md", z.namelist())
        self.assertEqual(set(self.report()["omitted_files"]), {"hooks.json", "commands/ignored.md"})

    def test_mcp_only_keeps_eligible_connection(self):
        self.manifest()
        self.put(".mcp.json", json.dumps({"mcpServers": {
            "docs": {"type": "http", "url": "https://example.org/mcp"},
            "desktop": {"command": "local-server", "env": {"KEY": "EXAMPLE_VALUE"}},
        }}))
        self.run_cli()
        with ZipFile(self.dest / "plugin.zip") as z:
            servers = json.loads(z.read("mcp.json"))["mcpServers"]
            self.assertEqual(servers, {"docs": {"type": "streamable-http", "url": "https://example.org/mcp"}})
            self.assertNotIn(".mcp.json", z.namelist())
        self.assertNotIn("EXAMPLE_VALUE", str(self.report()))

    def test_inline_command(self):
        self.manifest(commands={"brief": {"content": "Outline the supplied topic.", "description": "Draft an outline."}})
        self.run_cli()
        with ZipFile(self.dest / "skills/brief.zip") as z:
            self.assertIn("Outline the supplied topic.", z.read("brief/SKILL.md").decode())

    def test_unconvertible_plugin_explains_missing_port(self):
        self.manifest(mcpServers={"local": {"command": "server"}})
        self.assertIn("local", self.run_cli(ok=False).stderr)
        self.assertFalse(self.dest.exists())

    def test_collision_preserves_sources_and_creates_no_partial_output(self):
        self.manifest()
        self.put("skills/summary/SKILL.md", "Summarize.")
        self.put("commands/Summary.md", "Make a brief.")
        self.assertIn("distinct name", self.run_cli(ok=False).stderr)
        self.assertFalse(self.dest.exists())
        self.assertTrue((self.source / "commands/Summary.md").exists())

    def test_existing_destination_is_preserved(self):
        self.put("SKILL.md", "Collect feedback.")
        self.run_cli()
        archive = (self.dest / "plugin.zip").read_bytes()
        self.run_cli(ok=False)
        self.assertEqual(archive, (self.dest / "plugin.zip").read_bytes())

    def test_bad_zip_member_rejected(self):
        src = self.work / "bad.zip"
        with ZipFile(src, "w") as z:
            z.writestr("../outside.md", "Example")
        self.run_cli(src, ok=False)
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.work / "outside.md").exists())
