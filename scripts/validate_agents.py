#!/usr/bin/env python3
"""Check custom agent files before you commit them.

    python3 scripts/validate_agents.py             check the whole repo
    python3 scripts/validate_agents.py FILE ...    check only these agent files

Standard library only (Python 3.9 or newer). Exit code 1 if any check fails.
Warnings don't fail the run.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

SELF = Path(__file__).resolve()
ROOT = SELF.parent.parent
AGENTS_DIR = ROOT / ".github" / "agents"
README = ROOT / "README.md"

MAX_PROMPT_CHARS = 30000
RESERVED_NAMES = {
    "explore",
    "task",
    "general-purpose",
    "rubber-duck",
    "code-review",
    "research",
    "security-review",
}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yml", ".yaml", ".json", ".toml", ".txt"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}

# This repo is public. Nothing below may be committed.
SECRET_PATTERNS = [
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    (
        "credential assignment",
        re.compile(
            r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|client[_-]?secret)"
            r"\b\s*[:=]\s*[\"']?[A-Za-z0-9/+_.-]{12,}"
        ),
    ),
]
INTERNAL_PATTERNS = [
    ("Slack workspace link", re.compile(r"https?://[A-Za-z0-9-]+\.slack\.com/(?:archives|team|files|client)/", re.I)),
    ("SharePoint link", re.compile(r"https?://[A-Za-z0-9.-]*\.sharepoint\.com", re.I)),
    ("Teams link", re.compile(r"https?://teams\.(?:microsoft|live)\.com", re.I)),
    ("Dynamics link", re.compile(r"https?://[A-Za-z0-9.-]*\.crm\d*\.dynamics\.com", re.I)),
    ("Azure DevOps link", re.compile(r"https?://(?:dev\.azure\.com|[A-Za-z0-9-]+\.visualstudio\.com)", re.I)),
    ("corporate link", re.compile(r"https?://[A-Za-z0-9.-]*\.corp\.microsoft\.com", re.I)),
    (
        "UUID (tenant, project or app ID?)",
        re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    ),
    ("possible Slack ID", re.compile(r"\b[CUTWG](?=[A-Z0-9]*[0-9])[A-Z0-9]{8,10}\b")),
]
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "users.noreply.github.com", "github.com")

# Writing style for markdown: no emojis, no em or en dashes, no filler phrases.
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")
DASH_RE = re.compile("[\u2013\u2014]")
FILLER_PHRASES = [
    "let's dive in",
    "let's take a closer look",
    "it is important to note",
    "it's important to note",
    "in today's fast-paced",
    "plays a crucial role",
    "game-changing",
    "i hope this helps",
    "in conclusion",
]


class Report:
    """Collects findings and prints them as they come."""

    def __init__(self) -> None:
        self.errors = 0
        self.warnings = 0

    @staticmethod
    def _where(path: Path, line: int) -> str:
        try:
            shown = str(path.resolve().relative_to(ROOT))
        except ValueError:
            shown = str(path)
        return "%s:%d" % (shown, line) if line else shown

    def error(self, path: Path, line: int, message: str) -> None:
        self.errors += 1
        print("ERROR   %s: %s" % (self._where(path, line), message))

    def warn(self, path: Path, line: int, message: str) -> None:
        self.warnings += 1
        print("WARNING %s: %s" % (self._where(path, line), message))

    def info(self, path: Path, message: str) -> None:
        print("INFO    %s: %s" % (self._where(path, 0), message))


# ---------------------------------------------------------------------------
# Frontmatter: a small YAML subset. Anything it can't read fails loudly.
# ---------------------------------------------------------------------------

KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):(?:[ \t]+(.*))?$")
BLOCK_SCALAR_RE = re.compile(r"^[>|][+-]?[0-9]?$")


class NestedMap:
    """Stands in for a nested mapping such as mcp-servers. It isn't inspected."""


NESTED_MAP = NestedMap()


def split_frontmatter(text: str):
    lines = text.lstrip("\ufeff").split("\n")
    if lines[0].strip() != "---":
        raise ValueError("the file must start with a '---' line")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index], "\n".join(lines[index + 1:])
    raise ValueError("the frontmatter must end with a '---' line")


def strip_comment(value: str) -> str:
    """Drop a trailing ' # comment' that sits outside quotes."""
    quote = None
    for index, char in enumerate(value):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or value[index - 1] in " \t"):
            return value[:index].rstrip()
    return value.rstrip()


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_inline_list(text: str, lineno: int):
    if not text.endswith("]"):
        raise ValueError("line %d: an inline list must close on the same line" % lineno)
    items, current, quote = [], "", None
    for char in text[1:-1]:
        if quote:
            current += char
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            current += char
        elif char == ",":
            items.append(current)
            current = ""
        else:
            current += char
    items.append(current)
    return [unquote(item) for item in items if item.strip()]


def parse_frontmatter(lines):
    """Return {key: (value, file_line_number)}.

    Values are a string, a list of strings, or NESTED_MAP.
    """
    result = {}
    count = len(lines)
    i = 0
    while i < count:
        raw = lines[i]
        text = raw.strip()
        lineno = i + 2  # frontmatter starts on file line 2
        if not text or text.startswith("#"):
            i += 1
            continue
        if raw[0] in " \t":
            raise ValueError("line %d: unexpected indentation" % lineno)
        match = KEY_RE.match(raw.rstrip())
        if not match:
            raise ValueError("line %d: expected 'key: value'" % lineno)
        key = match.group(1)
        rest = strip_comment(match.group(2) or "")
        if key in result:
            raise ValueError("line %d: duplicate key '%s'" % (lineno, key))
        i += 1

        if BLOCK_SCALAR_RE.match(rest):
            block = []
            while i < count and (not lines[i].strip() or lines[i][0] in " \t"):
                block.append(lines[i].strip())
                i += 1
            joiner = "\n" if rest.startswith("|") else " "
            value = joiner.join(part for part in block if part)
        elif rest.startswith("["):
            value = parse_inline_list(rest, lineno)
        elif rest:
            value = unquote(rest)
        else:
            children = []
            while i < count:
                line = lines[i]
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or line[0] in " \t" or stripped == "-" or stripped.startswith("- "):
                    children.append((i, line))
                    i += 1
                else:
                    break
            significant = [(idx, ln) for idx, ln in children if ln.strip() and not ln.strip().startswith("#")]
            if not significant:
                value = ""
            else:
                indent = min(len(ln) - len(ln.lstrip()) for _, ln in significant)
                top = [(idx, ln) for idx, ln in significant if len(ln) - len(ln.lstrip()) == indent]
                if all(ln.strip() == "-" or ln.strip().startswith("- ") for _, ln in top):
                    value = []
                    for idx, ln in top:
                        item = unquote(strip_comment(ln.strip()[1:].strip()))
                        if not item:
                            raise ValueError("line %d: empty list item" % (idx + 2))
                        value.append(item)
                else:
                    value = NESTED_MAP
        result[key] = (value, lineno)
    return result


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_agent(path: Path, report: Report):
    """Validate one agent file. Returns its id (file stem) for the catalog check."""
    if not path.name.endswith(".agent.md"):
        report.error(path, 0, "agent files must be named <id>.agent.md")
        return None
    stem = path.name[: -len(".agent.md")]

    try:
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        frontmatter_lines, body = split_frontmatter(text)
        meta = parse_frontmatter(frontmatter_lines)
    except (OSError, UnicodeDecodeError) as exc:
        report.error(path, 0, "can't read file: %s" % exc)
        return None
    except ValueError as exc:
        report.error(path, 0, "frontmatter: %s" % exc)
        return stem

    def get(key):
        return meta[key][0] if key in meta else None

    def line_of(key):
        return meta[key][1] if key in meta else 0

    description = get("description")
    if not isinstance(description, str) or not description.strip():
        report.error(path, line_of("description"), "description is missing or empty")

    name = get("name")
    if not isinstance(name, str) or not name.strip():
        report.error(path, line_of("name"), "name is missing")
    else:
        if name != stem:
            report.error(path, line_of("name"), "name '%s' must match the file name '%s'" % (name, stem))
        if not NAME_RE.match(name):
            report.error(path, line_of("name"), "name must use lowercase letters, digits and single hyphens")
        if name in RESERVED_NAMES:
            report.error(path, line_of("name"), "name '%s' is reserved by a built-in agent" % name)

    prompt = body.strip()
    if not prompt:
        report.error(path, 0, "the prompt (the text after the frontmatter) is empty")
    elif len(prompt) > MAX_PROMPT_CHARS:
        report.error(path, 0, "prompt is %d characters, over the %d limit" % (len(prompt), MAX_PROMPT_CHARS))

    tools = get("tools")
    tool_count = 0
    if tools is None:
        report.warn(path, 0, "no tools list, so the agent gets every tool. List only what it needs.")
    elif isinstance(tools, NestedMap):
        report.warn(path, line_of("tools"), "tools should be a list of tool names")
    else:
        if isinstance(tools, str):
            tools = [tools] if tools else []
        tool_count = len(tools)
        if not tools:
            report.warn(path, line_of("tools"), "tools is empty, so the agent can't use any tool")
        seen = set()
        for tool in tools:
            if tool.endswith("*"):
                report.warn(path, line_of("tools"), "wildcard tool '%s' grants more than you may intend" % tool)
            if tool in seen:
                report.warn(path, line_of("tools"), "duplicate tool '%s'" % tool)
            seen.add(tool)

    report.info(path, "prompt %d chars, %d tools" % (len(prompt), tool_count))
    return stem


def scan_text(path: Path, report: Report) -> None:
    """Public-repo safety and writing-style checks for one text file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        report.error(path, 0, "can't read file: %s" % exc)
        return
    is_markdown = path.suffix.lower() == ".md"
    for number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                report.error(path, number, "looks like a secret (%s)" % label)
        for label, pattern in INTERNAL_PATTERNS:
            if pattern.search(line):
                report.error(path, number, "internal link or ID (%s), and this repo is public" % label)
        for match in EMAIL_RE.finditer(line):
            domain = match.group(1).lower()
            if not any(domain == ok or domain.endswith("." + ok) for ok in ALLOWED_EMAIL_DOMAINS):
                report.error(path, number, "email address, and this repo is public")
        if not is_markdown:
            continue
        if EMOJI_RE.search(line):
            report.error(path, number, "emoji or pictograph")
        if DASH_RE.search(line):
            report.error(path, number, "em or en dash: use a comma, colon, period or 'to'")
        lowered = line.lower().replace("\u2019", "'")
        for phrase in FILLER_PHRASES:
            if phrase in lowered:
                report.warn(path, number, "filler phrase '%s'" % phrase)


def check_catalog(agent_ids, report: Report) -> None:
    """Every agent needs a row in the README catalog table."""
    text = README.read_text(encoding="utf-8") if README.is_file() else ""
    rows = [line for line in text.splitlines() if line.lstrip().startswith("|")]
    for agent_id in agent_ids:
        if not any("`%s`" % agent_id in row for row in rows):
            report.error(README, 0, "no catalog row for agent '%s'. Add a table row that mentions `%s`." % (agent_id, agent_id))


def repo_text_files():
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in TEXT_SUFFIXES and path.resolve() != SELF:
                found.append(path)
    return sorted(found)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate custom agent files.")
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="agent files to check. With none, checks every agent in .github/agents, the README catalog and all text files.",
    )
    args = parser.parse_args(argv)
    report = Report()

    if args.files:
        agent_files = []
        for path in args.files:
            if path.is_file():
                agent_files.append(path)
            else:
                report.error(path, 0, "file not found")
        scan_files = list(agent_files)
    else:
        agent_files = sorted(AGENTS_DIR.glob("*.agent.md")) if AGENTS_DIR.is_dir() else []
        scan_files = repo_text_files()
        if not agent_files:
            report.error(AGENTS_DIR, 0, "no *.agent.md files found")
        if AGENTS_DIR.is_dir():
            for extra in sorted(AGENTS_DIR.iterdir()):
                if extra.is_file() and not extra.name.startswith(".") and not extra.name.endswith(".agent.md"):
                    report.warn(extra, 0, "not named <id>.agent.md, so the app ignores it")

    agent_ids = []
    for path in agent_files:
        agent_id = check_agent(path, report)
        if agent_id:
            agent_ids.append(agent_id)
    for path in scan_files:
        scan_text(path, report)
    if not args.files:
        check_catalog(agent_ids, report)

    print(
        "Checked %d agent file(s) and %d text file(s): %d error(s), %d warning(s)."
        % (len(agent_files), len(scan_files), report.errors, report.warnings)
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
