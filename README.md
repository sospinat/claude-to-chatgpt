# Claude to ChatGPT

Convert a Claude skill or Claude Code plugin into a ChatGPT plugin ZIP and individual skill ZIPs. Run the translator locally, or use the translator itself as a skill or plugin. The local conversion needs Python and PyYAML. It runs offline and requires no API key.

## Use it in ChatGPT

Choose one installation. The plugin already includes the translator skill.

| What you want | Download | Where to use it in ChatGPT web |
| --- | --- | --- |
| Mention the translator by name in a chat | [Plugin ZIP](https://raw.githubusercontent.com/sospinat/claude-to-chatgpt/main/downloads/claude-to-chatgpt.zip) | **Plugins → Add → Upload plugin archive → Add plugin → Install plugin → Try in chat** |
| Make the translator available as an individual skill | [Skill ZIP](https://raw.githubusercontent.com/sospinat/claude-to-chatgpt/main/downloads/translate-claude-package.zip) | **Plugins → Skills → Add → Upload from your computer**. Some workspaces label the button **Create**. |

Attach the Claude package you want to convert. Ask “Convert this Claude plugin for ChatGPT. Return the plugin ZIP, skill ZIPs and migration report. Preserve the original language and workflow rules.” The required upload options depend on your workspace and permissions. Workspace admins can also use **Admin console → Plugins → Add → Upload plugin**. [ChatGPT skills](https://help.openai.com/en/articles/20001066-skills-in-chatgpt) · [Plugin uploads](https://help.openai.com/en/articles/20001256-plugins-in-chatgpt)

### Prueba en español

1. Instala una de las dos opciones de la tabla. El plugin permite abrir la conversación desde **Try in chat**.
2. Adjunta [este pequeño plugin ficticio de Claude](https://raw.githubusercontent.com/sospinat/claude-to-chatgpt/main/examples/acta-de-ejemplo-claude.zip) y pide «Convierte el adjunto para ChatGPT en español. Conserva las reglas originales y entrégame los ZIP y el informe».
3. Abre la skill `resumir-acuerdos` de la salida. Su archivo `plantilla.txt` debe conservar el encabezado `ACTA-LILA-708` y las columnas `Acuerdo | Responsable | Fecha`. El original deja abierta la decisión sobre qué hacer cuando falta un dato.

## Run locally

With Python 3.10 or newer, run these commands from the repository root. Replace `path/to/claude-plugin` with the path to a plugin folder, skill folder, its SKILL.md, or a ZIP of either. Choose a new output directory outside the input.

```sh
python -m pip install -r requirements.txt
python plugins/claude-to-chatgpt/skills/translate-claude-package/scripts/translate.py path/to/claude-plugin --out converted
```

Open `converted/migration.json` to see each source-to-skill mapping, translated MCP servers, omitted files, and settings that need attention. Find the whole plugin in `converted/plugin.zip` and each individual upload in `converted/skills/`. For example, a plugin containing `commands/meeting-brief.md` produces `skills/meeting-brief/SKILL.md` in the plugin archive and `skills/meeting-brief.zip` alongside it.

For a Spanish workflow, append `--language es`. This controls the generated argument wording and fallback descriptions. Source prose stays in its original language. The CLI diagnostics and review notes are in English.

When you pass a single `SKILL.md`, the converter reads that file, sibling license notices and the conventional `scripts`, `references`, `assets`, `templates` and `agents` directories. Pass the dedicated skill folder or its ZIP to include custom resource locations.

## What carries over

| Claude input | ChatGPT output |
| --- | --- |
| SKILL.md and files inside its skill folder | Skill with a normalized name, description, instructions and bundled files |
| Markdown commands and agents | One skill for each procedure. Prose argument placeholders become explicit inputs |
| Shared resources referenced through a literal plugin-root variable | Copies of the referenced resource directory within the affected skill |
| Plain HTTPS MCP connection with explicit HTTP transport | Streamable HTTP declaration in the plugin ZIP. Verify authentication and tool access in the destination |
| Local servers, header-based credentials, hooks and other runtime configuration | Items for manual migration. Configuration values stay out of the migration report |
| Source license and notice files | Included with the converted workflows |

Instruction-based workflows with named templates are the best fit. A source that depends on a local server, lifecycle hook or authenticated tool needs an integration test in the target workspace. The migration report identifies the pieces to configure. A successful conversion demonstrates that the package was built.

The CLI handles default component folders, manifest-declared paths, and source or inline command maps. Supply a single plugin from a marketplace at a time. Packages containing only unsupported components return a diagnostic. The CLI preserves code examples and flags recognizable Claude references. Review the full instructions and scripts for tool availability and relative paths. Test one representative request in the destination workspace before sharing the workflow. [Claude manifest reference](https://code.claude.com/docs/en/plugins-reference) · [OpenAI migration guide](https://developers.openai.com/plugins/guides/submit-claude-plugin)

Conversion reads package contents without running the source's code. It skips common environment, dependency and version-control files and rejects linked entries. Other supporting files inside a skill are copied as supplied. Inspect the generated ZIP before distributing it. The converter accepts up to 4,096 files and 64 MiB of uncompressed source files.

## Verify the translator

```sh
python -m unittest discover -s tests
```

The repository includes a Codex marketplace catalog at `.agents/plugins/marketplace.json`. The packaged translator lives in `plugins/claude-to-chatgpt/`. [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins)

The translator is free under the [MIT License](LICENSE). Converted material retains its source licensing.
