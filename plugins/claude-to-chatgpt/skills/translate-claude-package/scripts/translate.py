"""Build ChatGPT skill and plugin archives from a Claude package. Python 3.10+."""
import argparse
import io
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import sys
import tempfile
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

try:
    import yaml
except ImportError:
    raise SystemExit("Install the YAML parser first: python -m pip install 'PyYAML>=6,<7'")

SCHEMA = "https://agent-plugins.org/schemas/1.0.0/"
CLAUDE_MANIFEST = ".claude-plugin/plugin.json"
MAX_BYTES = 64 * 1024 * 1024
MAX_FILES = 4096
SKIP = {".git", ".hg", ".svn", ".venv", "node_modules", "__pycache__", "__MACOSX", ".DS_Store"}
HEADER = re.compile(r"\A---[ \t]*\n(.*?)^---[ \t]*(?:\n|\Z)", re.M | re.S)
LEGAL = re.compile(r"(license|licence|notice|copying)(?:[.-].*)?$", re.I)
ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
SHARED = {"scripts", "references", "assets", "templates"}
RUNTIME = re.compile(r"!\x60|^!command\b|CLAUDE_[A-Z_]+|\$\{user_config\.|\$ARGUMENTS|\$\d+\b|mcp__|\.claude/|(?i:\bClaude Code\b|\b(?:Bash|Read|Write|Edit|Grep|Glob|Task)\s*\()", re.M)


def clean_path(name):
    parts = name.split("/")
    if any(not part or part in {".", ".."} or part.endswith((" ", "."))
           or PureWindowsPath(part).is_reserved() or re.search(r'[\\:*?"<>|\x00-\x1f]', part)
           for part in parts):
        raise ValueError(f"Invalid portable package path: {name!r}")
    return name


def ignored(name):
    parts = name.split("/")
    return any(p in SKIP or p == ".env" or p.startswith(".env.") for p in parts)


def plugin_layout(files):
    return CLAUDE_MANIFEST in files or ("SKILL.md" not in files and
        (".mcp.json" in files or any(k.startswith(("skills/", "commands/", "agents/")) for k in files)))


def read_package(source):
    files, spelling, directories = {}, {}, set()
    total = count = 0

    def add(name, size, read):
        nonlocal total, count
        clean_path(name)
        count += 1
        total += size
        if count > MAX_FILES or total > MAX_BYTES:
            raise ValueError("Input exceeds 4096 files or 64 MiB uncompressed.")
        parts = name.split("/")
        for i in range(1, len(parts) + 1):
            prefix = "/".join(parts[:i])
            key = prefix.casefold()
            if spelling.setdefault(key, prefix) != prefix:
                raise ValueError(f"Ambiguous case in path: {prefix}")
            if i < len(parts):
                if prefix in files:
                    raise ValueError(f"File used as directory: {prefix}")
                directories.add(prefix)
        if name in files or name in directories:
            raise ValueError(f"Duplicate or conflicting path: {name}")
        files[name] = read()

    if source.is_dir():
        def fail(error):
            raise error
        for folder, dirs, names in os.walk(source, onerror=fail):
            dirs[:] = sorted(d for d in dirs if not ignored(d))
            for item in dirs + sorted(names):
                path = Path(folder, item)
                name = path.relative_to(source).as_posix()
                if ignored(name):
                    continue
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0) in (0xA0000003, 0xA000000C):
                    raise ValueError(f"Linked path requires a regular copy: {name}")
                if item in dirs:
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError(f"Unsupported file type: {name}")
                add(name, info.st_size, path.read_bytes)
        return files, source.resolve().name
    with ZipFile(source) as archive:
        for item in archive.infolist():
            name = clean_path(item.filename.rstrip("/"))
            if ignored(name):
                continue
            if stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1:
                raise ValueError(f"Linked or encrypted ZIP entry: {name}")
            if not item.is_dir():
                add(name, item.file_size, lambda: archive.read(item))
    label = source.stem
    while files and "SKILL.md" not in files and not plugin_layout(files):
        roots = {k.split("/", 1)[0] for k in files}
        if len(roots) != 1 or any("/" not in k for k in files):
            break
        label = roots.pop()
        files = {k.split("/", 1)[1]: v for k, v in files.items()}
    return files, label


def slug(value):
    if not isinstance(value, str):
        raise ValueError("Package and skill names must be strings.")
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:64].rstrip("-")
    if not result:
        raise ValueError(f"Supply a name containing a Latin letter or digit for {value!r}.")
    clean_path(result)
    return result


def as_json(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def read_object(data, label):
    obj = json.loads(data.decode("utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError(f"Expected a JSON object in {label}.")
    return obj


def parse_skill(data):
    text = data.decode("utf-8-sig").replace("\r\n", "\n")
    header = HEADER.match(text)
    if header:
        meta = yaml.safe_load(header[1]) or {}
        if not isinstance(meta, dict) or any(not isinstance(k, str) for k in meta):
            raise ValueError("Skill frontmatter must be a YAML mapping with text keys.")
        return meta, text[header.end():].strip()
    if text.splitlines()[:1] == ["---"]:
        raise ValueError("Unterminated YAML frontmatter.")
    return {}, text.strip()


def entries(files, manifest, kind, notes):
    paths = manifest.get(kind, [])
    if isinstance(paths, str):
        paths = [paths]
    if isinstance(paths, dict) and kind == "commands":
        for key, spec in paths.items():
            if not isinstance(spec, dict):
                raise ValueError(f"Invalid command entry: {key}")
            if "source" in spec:
                path = clean_path(spec["source"].removeprefix("./"))
                yield path, key, files[path], spec.get("description")
            else:
                yield "commands/" + clean_path(key) + ".md", key, spec["content"].encode(), spec.get("description")
            if set(spec) - {"source", "content", "description"}:
                notes.append(f"Review command options for {key}.")
        return
    if not isinstance(paths, list):
        raise ValueError(f"Expected paths for {kind}.")
    if kind == "skills" or kind not in manifest:
        paths = [kind, *paths]
    found = set()
    for raw in paths:
        path = clean_path(raw.removeprefix("./").rstrip("/"))
        prefix = path + "/"
        candidates = [k for k in sorted(files) if k == path or k.startswith(prefix)]
        if kind == "skills":
            candidates = [k for k in candidates if k.rsplit("/", 1)[-1] == "SKILL.md"]
        else:
            candidates = [k for k in candidates if k.lower().endswith(".md")]
        if not candidates and raw in ([manifest.get(kind)] if isinstance(manifest.get(kind), str) else manifest.get(kind, [])):
            notes.append(f"Check declared {kind} path {path}. No matching Markdown file was found.")
        for k in candidates:
            if k in found:
                continue
            found.add(k)
            name = Path(k).parent.name if kind == "skills" else Path(k).stem
            yield k, name, files[k], None


def convert_servers(files, manifest, notes, covered):
    """Translate static HTTP declarations. Connection and auth stay a host-side test."""
    config = manifest.get("mcpServers", [])
    sources = config if isinstance(config, list) else [config]
    if ".mcp.json" in files:
        sources = [".mcp.json", *sources]
    servers = {}
    for source in sources:
        if isinstance(source, str):
            key = clean_path(source.removeprefix("./"))
            record = read_object(files[key], key)
            covered.add(key)
        else:
            record = source
        if not isinstance(record, dict):
            raise ValueError("Expected an MCP server mapping or a local JSON file.")
        for name, spec in record.get("mcpServers", record).items():
            if name in servers:
                raise ValueError(f"Duplicate MCP server declaration: {name}")
            if isinstance(spec, dict) and isinstance(spec.get("url"), str):
                url = urlsplit(spec["url"])
                if (spec.get("type") == "http" and set(spec) == {"type", "url"}
                        and url.scheme == "https" and url.hostname and not url.username
                        and not url.password and not url.query and not url.fragment
                        and not re.search(r"[\s${}\\]", spec["url"]) and ID.fullmatch(name)):
                    servers[name] = {"type": "streamable-http", "url": spec["url"]}
                    notes.append(f"MCP server {name}: verify the endpoint, authentication and tool access in the target workspace.")
                    continue
            notes.append(f"MCP server {name}: configure transport and authentication manually. Source settings were omitted.")
    return servers


def convert(files, label):
    plugin = plugin_layout(files)
    manifest = read_object(files[CLAUDE_MANIFEST], CLAUDE_MANIFEST) if CLAUDE_MANIFEST in files else {}
    notes, mappings, out, skill_zips = [], [], {}, {}
    covered = {CLAUDE_MANIFEST}
    if plugin:
        sources = [(kind, item) for kind in ("skills", "commands", "agents")
                   for item in entries(files, manifest, kind, notes)]
        for key in sorted(set(manifest) - {"name", "description", "version", "license", "author",
                                            "skills", "commands", "agents", "mcpServers"}):
            notes.append(f"Review plugin manifest field '{key}' in the source. It was omitted.")
    elif "SKILL.md" in files:
        sources = [("skills", ("SKILL.md", label, files["SKILL.md"], None))]
    else:
        raise ValueError("Select one skill containing SKILL.md or one plugin containing .claude-plugin/plugin.json.")
    legal = {k: v for k, v in files.items() if "/" not in k and LEGAL.fullmatch(k)}
    out.update(legal)
    covered.update(legal)
    for kind, (path, fallback, data, description) in sources:
        meta, body = parse_skill(data)
        if not body:
            raise ValueError(f"Empty instructions in {path}.")
        name = slug(meta.get("name", fallback))
        if name in skill_zips:
            raise ValueError(f"Multiple workflows map to '{name}'. Give each one a distinct name.")
        desc = description or meta.get("description")
        if not desc:
            desc = f"Use the {name.replace('-', ' ')} workflow when requested."
            notes.append(f"{path}: refine the generated trigger description.")
        if not isinstance(desc, str) or len(desc.strip()) > 1024 or not desc.strip() or re.search("[<>]", desc):
            raise ValueError(f"Use a 1–1024 character description without angle brackets in {path}.")
        header = {"name": name, "description": desc.strip()}
        if isinstance(meta.get("license"), str):
            header["license"] = meta["license"]
        extra = sorted(set(meta) - set(header))
        if extra:
            notes.append(f"{path}: review source frontmatter fields {', '.join(extra)}.")
        bundle = {}
        prefix = path.removesuffix("SKILL.md") if kind == "skills" else None
        if prefix is not None:
            for k, v in files.items():
                if k.startswith(prefix):
                    bundle[k[len(prefix):]] = v
                    covered.add(k)
        covered.add(path)
        for k, v in legal.items():
            if k in bundle and bundle[k] != v:
                bundle["plugin-license/" + k] = v
            else:
                bundle[k] = v

        if plugin:
            for directory in sorted(SHARED):
                token = "\x24{CLAUDE_PLUGIN_ROOT}/" + directory + "/"
                if token in body and any(k.startswith(directory + "/") for k in files):
                    for k, v in files.items():
                        if k.startswith(directory + "/"):
                            target = "plugin-resources/" + k
                            if target in bundle and bundle[target] != v:
                                raise ValueError(f"Bundled resource collision: {target}")
                            bundle[target] = v
                            covered.add(k)
                    body = body.replace(token, "plugin-resources/" + directory + "/")
                    notes.append(f"{path}: resolve plugin-resources paths from the translated skill directory.")
        # Substitute workflow arguments only in prose. Keep code examples literal.
        in_fence = None
        converted = []
        for line in body.splitlines():
            fence = re.match(r"^\s*(\x60{3,}|~{3,})", line)
            if fence:
                mark = fence[1]
                if in_fence is None:
                    in_fence = mark
                elif mark.startswith(in_fence):
                    in_fence = None
            elif in_fence is None and "\x60" not in line and not line.startswith(("    ", "\t", "!")):
                line = re.sub(r"\bYou are Claude(?: Code)?(?=[,.])", "You are ChatGPT", line)
                line = re.sub(r"\$ARGUMENTS\[(\d+)\]", lambda m: f"argument {int(m[1]) + 1} from the user's request", line)
                line = re.sub(r"\$ARGUMENTS\b", "the arguments provided by the user", line)
            converted.append(line)
        body = "\n".join(converted)
        if RUNTIME.search(body):
            notes.append(f"{path}: adapt remaining Claude runtime references or tool calls in the body.")
        if meta.get("disable-model-invocation") is True:
            body = "Use this workflow only when the user explicitly requests it.\n\n" + body
            config = yaml.safe_load(bundle.get("agents/openai.yaml", b"{}")) or {}
            config.setdefault("policy", {})["allow_implicit_invocation"] = False
            bundle["agents/openai.yaml"] = yaml.safe_dump(config).encode()
        if kind == "agents":
            notes.append(f"{path}: translated the procedure into a skill. Check any reliance on subagent isolation.")
        bundle["SKILL.md"] = ("---\n" + yaml.safe_dump(header, sort_keys=False, allow_unicode=True)
                              + "---\n\n" + body + "\n").encode()
        skill_zips[name] = bundle
        mappings.append({"source": path, "skill": name})
        out.update({f"skills/{name}/{k}": v for k, v in bundle.items()})
    servers = convert_servers(files, manifest, notes, covered) if plugin else {}
    if servers:
        out["mcp.json"] = as_json({"$schema": SCHEMA + "mcp.schema.json", "mcpServers": servers})
    if not mappings and not servers:
        details = " ".join(notes) or "Inspect the plugin components and port the workflow manually."
        raise ValueError("No convertible skills, commands or agents. " + details)
    plugin_name = slug(manifest.get("name", label)) if plugin else mappings[0]["skill"]
    plugin_meta = {"$schema": SCHEMA + "plugin.schema.json", "name": plugin_name,
                   "description": manifest.get("description") or f"Workflows from {plugin_name}."}
    for key in ("version", "license"):
        if isinstance(manifest.get(key), str):
            plugin_meta[key] = manifest[key]
    if not isinstance(plugin_meta["description"], str):
        raise ValueError("Plugin description must be text.")
    author = manifest.get("author")
    if isinstance(author, dict):
        plugin_meta["author"] = {k: author[k] for k in ("name", "email", "url") if isinstance(author.get(k), str)}
    out["plugin.json"] = as_json(plugin_meta)
    omitted = sorted(set(files) - covered)
    report = {"package": plugin_name, "converted": mappings, "mcp_servers": sorted(servers),
              "manual_review": notes, "omitted_files": omitted}
    return out, skill_zips, report


def archive_bytes(files):
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        for name, data in sorted(files.items()):
            item = ZipInfo(clean_path(name))
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data, compress_type=ZIP_DEFLATED)
    return stream.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Local skill or plugin directory or ZIP, or its SKILL.md")
    parser.add_argument("--out", required=True, type=Path, help="New output directory")
    args = parser.parse_args()
    source = args.source.resolve()
    if source.name == "SKILL.md" and source.is_file():
        source = source.parent
    dest = args.out.resolve()
    if dest.exists():
        parser.exit(2, "Choose a new output directory.\n")
    if dest.is_relative_to(source):
        parser.exit(2, "Choose an output directory outside the source package.\n")
    try:
        files, label = read_package(source)
        package, skills, report = convert(files, label)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=dest.parent) as temp:
            staging = Path(temp, "result")
            staging.mkdir()
            (staging / "plugin.zip").write_bytes(archive_bytes(package))
            (staging / "skills").mkdir()
            for name, members in skills.items():
                (staging / "skills" / (name + ".zip")).write_bytes(archive_bytes(
                    {name + "/" + k: v for k, v in members.items()}))
            (staging / "migration.json").write_bytes(as_json(report))
            staging.rename(dest)
    except (OSError, BadZipFile, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError, RuntimeError) as err:
        parser.exit(2, f"Conversion failed: {err}\n")
    print(f"Created {dest / 'plugin.zip'} and {len(skills)} skill ZIP(s).")
    print(f"Review {dest / 'migration.json'} ({len(report['manual_review'])} notes, "
          f"{len(report['omitted_files'])} omitted files).")


if __name__ == "__main__":
    main()
