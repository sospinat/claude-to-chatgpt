# Claude to ChatGPT

Convert a Claude skill or Claude Code plugin into a ChatGPT plugin ZIP and individual skill ZIPs. Run the translator locally, or use the translator itself as a skill or plugin. The local conversion needs Python and PyYAML. It runs offline and requires no API key.

## Use it in ChatGPT

Download the [translator skill ZIP](downloads/translate-claude-package.zip) or the [translator plugin ZIP](downloads/claude-to-chatgpt.zip). In ChatGPT, open **Plugins → Skills → Create → Upload from your computer** for the skill. Workspace owners or admins with plugin upload access can import the plugin ZIP under **Admin console → Plugins → Add → Upload plugin**. Availability depends on the workspace. [ChatGPT skills](https://help.openai.com/en/articles/20001066-skills-in-chatgpt) · [Plugin uploads](https://help.openai.com/en/articles/20001256-plugins-in-chatgpt)

Attach your Claude package and ask “Translate this Claude plugin for ChatGPT. Give me the ZIP and tell me which steps need manual setup.” The translator skill can adapt the instructions in chat and review the generated workflows against the source.

## Run locally

With Python 3.10 or newer, run these commands from the repository root. Replace `path/to/claude-plugin` with the path to a plugin folder, skill folder, its SKILL.md, or a ZIP of either. Choose a new output directory outside the input.

```sh
python -m pip install -r requirements.txt
python plugins/claude-to-chatgpt/skills/translate-claude-package/scripts/translate.py path/to/claude-plugin --out converted
```

Open `converted/migration.json` to see each source-to-skill mapping, translated MCP servers, omitted files, and settings that need attention. Find the whole plugin in `converted/plugin.zip` and each individual upload in `converted/skills/`. For example, a plugin containing `commands/meeting-brief.md` produces `skills/meeting-brief/SKILL.md` in the plugin archive and `skills/meeting-brief.zip` alongside it.

## What carries over

| Claude input | ChatGPT output |
| --- | --- |
| SKILL.md and files inside its skill folder | Skill with a normalized name, description, instructions and bundled files |
| Markdown commands and agents | One skill for each procedure. Prose argument placeholders become explicit inputs |
| Shared resources referenced through a literal plugin-root variable | Copies of the referenced resource directory within the affected skill |
| Plain HTTPS MCP connection with explicit HTTP transport | Streamable HTTP declaration in the plugin ZIP. Verify authentication and tool access in the destination |
| Local servers, header-based credentials, hooks and other runtime configuration | Items for manual migration. Configuration values stay out of the migration report |
| Source license and notice files | Included with the converted workflows |

The CLI handles default component folders, manifest-declared paths, and source or inline command maps. Supply a single plugin from a marketplace at a time. Packages containing only unsupported components return a diagnostic. The CLI preserves code examples and flags recognizable Claude references. Review the full instructions and scripts for tool availability and relative paths. Test one representative request in the destination workspace before sharing the workflow. [Claude manifest reference](https://code.claude.com/docs/en/plugins-reference) · [OpenAI migration guide](https://developers.openai.com/plugins/guides/submit-claude-plugin)

Conversion reads package contents without running the source's code. It skips common environment, dependency and version-control files and rejects linked entries. Other supporting files inside a skill are copied as supplied. Inspect the generated ZIP before distributing it. The converter accepts up to 4,096 files and 64 MiB of uncompressed source files.

## Verify the translator

```sh
python -m unittest discover -s tests
```

The repository includes a Codex marketplace catalog at `.agents/plugins/marketplace.json`. The packaged translator lives in `plugins/claude-to-chatgpt/`. [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins)

The translator is free under the [MIT License](LICENSE). Converted material retains its source licensing.
