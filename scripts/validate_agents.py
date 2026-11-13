#!/usr/bin/env python3
"""Check custom agent files before you commit them.

    python3 scripts/validate_agents.py             check the whole repo
    python3 scripts/validate_agents.py FILE ...    check only these files

Files named *.agent.md, or placed in .github/agents, get the agent checks.
Every file also gets the public-repo safety scan, and Markdown files get the
writing-style check.

The frontmatter parser reads a small YAML subset: "key: value" pairs, quoted or
plain one-line strings, true or false, inline lists, "- " lists, and ">-" or
"|" block text. Anything else is an error, so a typo can't silently change
what the agent is allowed to do.

Standard library only (Python 3.9 or newer). Exit code 1 if any check fails.
Warnings and INFO lines don't fail the run.
"""
from __future__ import annotations

import argparse
import codecs
import difflib
import os
import re
import subprocess
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
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}

# Frontmatter keys the platform documents. The app ignores a typo such as
# "tool:", and the agent would then get every tool.
KNOWN_KEYS = {
    "name", "description", "target", "tools", "model", "models", "modelPolicy",
    "model-policy", "reasoningEffort", "infer", "disable-model-invocation",
    "user-invocable", "mcp-servers", "metadata", "include-custom-instructions",
    "strict-tools-list", "sidekick", "argument-hint", "handoffs",
}
BOOLEAN_KEYS = (
    "infer", "disable-model-invocation", "user-invocable",
    "include-custom-instructions", "strict-tools-list",
)
# Tool aliases and name words that mean the agent can change something.
WRITE_ALIASES = {"edit", "execute", "shell", "bash", "powershell", "agent", "write"}
WRITE_WORDS = {
    "edit", "write", "send", "post", "create", "update", "delete", "remove",
    "push", "merge", "archive", "schedule", "draft", "react", "reaction",
    "reply", "upload", "run", "exec", "accept", "approve", "submit", "add",
    "set", "move", "rename", "save", "append", "insert", "assign", "close",
}

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
            r"(?i)(?<![A-Za-z0-9])(?:password|passwd|secret|secret[_-]?key|api[_-]?key"
            r"|(?:access|auth|refresh)[_-]?token|client[_-]?secret|private[_-]?key)"
            r"(?![A-Za-z0-9])\s*[:=]\s*[\"']?[A-Za-z0-9/+_.-]{12,}"
        ),
    ),
]
INTERNAL_PATTERNS = [
    (
        "Slack workspace link",
        re.compile(r"https?://[A-Za-z0-9.-]+\.slack\.com/(?:archives|team|files(?:-pri|-tmb)?|client)/", re.I),
    ),
    ("SharePoint link", re.compile(r"https?://[A-Za-z0-9.-]*\.sharepoint\.com", re.I)),
    ("Teams link", re.compile(r"https?://teams\.(?:microsoft\.com|live\.com|cloud\.microsoft)", re.I)),
    (
        "Outlook mail or calendar link",
        re.compile(r"https?://outlook\.(?:office|office365|live)\.com/(?:mail|calendar|owa)", re.I),
    ),
    ("Dynamics link", re.compile(r"https?://[A-Za-z0-9.-]*\.crm\d*\.dynamics\.com", re.I)),
    ("Azure DevOps link", re.compile(r"https?://(?:dev\.azure\.com|[A-Za-z0-9-]+\.visualstudio\.com)", re.I)),
    ("Kusto cluster link", re.compile(r"https?://[A-Za-z0-9.-]+\.kusto\.windows\.net", re.I)),
    ("Power BI link", re.compile(r"https?://(?:[A-Za-z0-9-]+\.)*powerbi\.com", re.I)),
    ("corporate link", re.compile(r"https?://[A-Za-z0-9.-]*\.corp\.microsoft\.com", re.I)),
]
UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
PLACEHOLDER_UUIDS = {"12345678-1234-1234-1234-123456789012"}
WARN_PATTERNS = [
    ("possible Slack ID", re.compile(r"(?<!\\)\b[CUTWG](?=[A-Z0-9]*[0-9][A-Z0-9]*[0-9])[A-Z0-9]{8,10}\b")),
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

FRONTMATTER_DELIMITER_RE = re.compile(r"^---[ \t]*$")
KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):(?:[ \t]+(.*))?$")
BLOCK_SCALAR_RE = re.compile(r"^[>|][+-]?[0-9]?$")
PLAIN_COMMENT_RE = re.compile(r"(?:^|[ \t])#")
TRAILING_COMMENT_RE = re.compile(r"[ \t]+#")
MAP_ITEM_RE = re.compile(r"^[A-Za-z0-9_-]+:(?:[ \t]|$)")
COLON_SPACE_RE = re.compile(r":(?:[ \t]|$)")
SIMPLE_ESCAPES = {
    "0": "\0", "a": "\a", "b": "\b", "t": "\t", "n": "\n", "v": "\v", "f": "\f",
    "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\",
}
HEX_ESCAPE_WIDTHS = {"x": 2, "u": 4, "U": 8}
HEX_DIGITS = "0123456789abcdefABCDEF"


class NestedMap:
    """Stands in for a nested mapping such as mcp-servers. It isn't inspected."""


NESTED_MAP = NestedMap()


def split_frontmatter(text: str):
    lines = text.lstrip("\ufeff").split("\n")
    if not FRONTMATTER_DELIMITER_RE.match(lines[0]):
        raise ValueError("the file must start with a '---' line")
    for index in range(1, len(lines)):
        if FRONTMATTER_DELIMITER_RE.match(lines[index]):
            return lines[1:index], "\n".join(lines[index + 1:])
    raise ValueError("the frontmatter must end with a '---' line at the start of a line")


def read_quoted(text: str, start: int):
    """Read the quoted string that begins at text[start]. Returns (value, index after it)."""
    quote = text[start]
    out = []
    i = start + 1
    while i < len(text):
        char = text[i]
        if quote == '"' and char == "\\":
            escape = text[i + 1:i + 2]
            if not escape:
                break
            if escape in SIMPLE_ESCAPES:
                out.append(SIMPLE_ESCAPES[escape])
                i += 2
            elif escape in HEX_ESCAPE_WIDTHS:
                width = HEX_ESCAPE_WIDTHS[escape]
                digits = text[i + 2:i + 2 + width]
                if len(digits) != width or any(d not in HEX_DIGITS for d in digits):
                    raise ValueError("bad \\%s escape in a double-quoted string" % escape)
                out.append(chr(int(digits, 16)))
                i += 2 + width
            else:
                raise ValueError("unsupported escape '\\%s' in a double-quoted string" % escape)
            continue
        if char == quote:
            if quote == "'" and text[i + 1:i + 2] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), i + 1
        out.append(char)
        i += 1
    raise ValueError("a quoted string is missing its closing quote")


def strip_plain_comment(text: str) -> str:
    """Drop a ' # comment' from unquoted text."""
    match = PLAIN_COMMENT_RE.search(text)
    return (text[:match.start()] if match else text).strip()


def parse_scalar(text: str, allow_bool: bool = True):
    """Parse a one-line value: a quoted string, a plain string, or true or false."""
    text = text.strip()
    if text[:1] in ("'", '"'):
        value, end = read_quoted(text, 0)
        tail = text[end:]
        if tail.strip() and not TRAILING_COMMENT_RE.match(tail):
            raise ValueError("unexpected text after the closing quote")
        return value
    plain = strip_plain_comment(text)
    if not plain:
        return ""
    first = plain[0]
    if first == "{":
        raise ValueError("inline maps aren't supported here. Use an indented block.")
    if first in "&*!|>%@`[]}":
        raise ValueError("a plain value can't start with '%s'. Put it in quotes." % first)
    if plain.startswith("- "):
        raise ValueError("a '- ' item can't sit on the key line. Use '[a, b]' or indented '- ' lines.")
    if COLON_SPACE_RE.search(plain):
        raise ValueError("a plain value can't contain ': '. Put it in quotes, or use '>-' and an indented block.")
    if plain in ("null", "Null", "NULL", "~"):
        raise ValueError("a null value isn't supported. Remove the key or write text.")
    if allow_bool and plain in ("true", "True", "TRUE"):
        return True
    if allow_bool and plain in ("false", "False", "FALSE"):
        return False
    return plain


def parse_flow_list(text: str):
    """Parse an inline list such as [read, "web", 'a, b'] that sits on one line."""
    missing_end = "an inline list must end with ']' on the same line. Use '- ' items for a longer list."
    items = []
    i, length = 1, len(text)
    while True:
        while i < length and text[i] in " \t":
            i += 1
        if i >= length:
            raise ValueError(missing_end)
        if text[i] == "]":
            i += 1
            break
        if text[i] in "'\"":
            item, i = read_quoted(text, i)
        else:
            start = i
            while i < length and text[i] not in ",]":
                i += 1
            if i >= length:
                raise ValueError(missing_end)
            raw = text[start:i].strip()
            if not raw:
                raise ValueError("empty item in an inline list")
            if PLAIN_COMMENT_RE.search(raw):
                raise ValueError("a '#' comment can't sit inside an inline list")
            item = parse_scalar(raw, allow_bool=False)
        if not item:
            raise ValueError("empty item in an inline list")
        items.append(item)
        while i < length and text[i] in " \t":
            i += 1
        if i >= length:
            raise ValueError(missing_end)
        if text[i] == ",":
            i += 1
        elif text[i] == "]":
            i += 1
            break
        else:
            raise ValueError("expected ',' or ']' after a list item")
    tail = text[i:]
    if tail.strip() and not TRAILING_COMMENT_RE.match(tail):
        raise ValueError("unexpected text after ']'")
    return items


def at_line(lineno: int, func, *args, **kwargs):
    """Call a parser function and add the file line number to any error."""
    try:
        return func(*args, **kwargs)
    except ValueError as exc:
        raise ValueError("line %d: %s" % (lineno, exc))


def read_block_scalar(lines, i: int, header: str):
    """Read the indented lines under '>-' or '|'. Returns (text, next line index)."""
    block = []
    while i < len(lines) and (not lines[i].strip() or lines[i][0] in " \t"):
        block.append(lines[i].strip())
        i += 1
    joiner = "\n" if header.startswith("|") else " "
    return joiner.join(part for part in block if part), i


def read_children(lines, i: int):
    """Read the lines under a bare 'key:'. Returns (value, next line index).

    The value is a list of strings, NESTED_MAP for anything more complex, or an
    empty string when nothing is indented under the key.
    """
    start = i
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line[0] in " \t" or stripped == "-" or stripped.startswith("- "):
            i += 1
        else:
            break
    significant = [
        (n, lines[n].rstrip())
        for n in range(start, i)
        if lines[n].strip() and not lines[n].strip().startswith("#")
    ]
    if not significant:
        return "", i
    first = significant[0][1].strip()
    if first != "-" and not first.startswith("- "):
        return NESTED_MAP, i

    indent = len(significant[0][1]) - len(significant[0][1].lstrip())
    items = []
    opaque = False
    for n, line in significant:
        lineno = n + 2
        stripped = line.strip()
        depth = len(line) - len(line.lstrip())
        if depth > indent:
            opaque = True
            continue
        if depth < indent or (stripped != "-" and not stripped.startswith("- ")):
            raise ValueError("line %d: this line doesn't line up with the '- ' items above it" % lineno)
        item_text = stripped[1:].strip()
        if MAP_ITEM_RE.match(item_text):
            opaque = True
            continue
        item = at_line(lineno, parse_scalar, item_text, allow_bool=False)
        if not item:
            raise ValueError("line %d: empty list item" % lineno)
        items.append(item)
    return (NESTED_MAP if opaque else items), i


def parse_frontmatter(lines):
    """Return {key: (value, file_line_number)}.

    A value is a string, a bool, a list of strings, or NESTED_MAP.
    """
    result = {}
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip()
        lineno = i + 2  # the frontmatter starts on file line 2
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if raw[0] in " \t":
            raise ValueError(
                "line %d: unexpected indentation. A value that continues on the next line needs '>-' after the key."
                % lineno
            )
        match = KEY_RE.match(raw)
        if not match:
            raise ValueError("line %d: expected 'key: value'" % lineno)
        key = match.group(1)
        rest = (match.group(2) or "").strip()
        if key in result:
            raise ValueError("line %d: duplicate key '%s'" % (lineno, key))
        i += 1

        head = strip_plain_comment(rest)
        if not head:
            value, i = read_children(lines, i)
        elif BLOCK_SCALAR_RE.match(head):
            value, i = read_block_scalar(lines, i, head)
        elif rest.startswith("["):
            value = at_line(lineno, parse_flow_list, rest)
        else:
            value = at_line(lineno, parse_scalar, rest)
        result[key] = (value, lineno)
    return result


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def is_write_capable(tool: str) -> bool:
    """True for tools that can change files, send messages or change records."""
    lowered = tool.lower()
    if lowered in WRITE_ALIASES:
        return True
    return any(word in WRITE_WORDS for word in re.split(r"[/_.\-]+", lowered))


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

    for key in meta:
        if key not in KNOWN_KEYS:
            close = difflib.get_close_matches(key, sorted(KNOWN_KEYS), n=1, cutoff=0.6)
            hint = " Did you mean '%s'?" % close[0] if close else ""
            report.error(
                path,
                line_of(key),
                "unknown frontmatter key '%s'.%s The app ignores unknown keys, so a typo can change what the agent may do." % (key, hint),
            )
    for key in BOOLEAN_KEYS:
        if key in meta and not isinstance(get(key), bool):
            report.error(path, line_of(key), "%s must be true or false" % key)

    description = get("description")
    if not isinstance(description, str):
        report.error(
            path,
            line_of("description"),
            "description is missing" if description is None else "description must be text",
        )
    elif not description.strip():
        report.error(path, line_of("description"), "description is empty")

    name = get("name")
    if not isinstance(name, str):
        report.error(path, line_of("name"), "name is missing" if name is None else "name must be text")
    elif not name.strip():
        report.error(path, line_of("name"), "name is empty")
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
    tool_names = []
    if "tools" not in meta:
        report.error(path, 0, "tools is missing, and an agent without it gets every tool. List only what it needs.")
    elif not isinstance(tools, (str, list)):
        report.error(path, line_of("tools"), "tools must be a list of tool names")
    else:
        for entry in [tools] if isinstance(tools, str) else tools:
            tool_names.extend(part.strip() for part in entry.split(",") if part.strip())
        if not tool_names:
            report.error(path, line_of("tools"), "tools is empty. List the tools the agent needs.")
        seen = set()
        for tool in tool_names:
            if "*" in tool:
                report.error(
                    path,
                    line_of("tools"),
                    "wildcard tool '%s'. Name each tool so the agent gets only what it needs." % tool,
                )
            if tool in seen:
                report.warn(path, line_of("tools"), "duplicate tool '%s'" % tool)
            seen.add(tool)
        risky = sorted(tool for tool in seen if is_write_capable(tool))
        if risky:
            report.info(path, "write-capable tools granted: %s" % ", ".join(risky))

    report.info(path, "prompt %d chars, %d tools" % (len(prompt), len(tool_names)))
    return stem


def load_text(path: Path):
    """Read a file for scanning. Returns (text, problem).

    text is None for a binary file. problem is "invalid" when the bytes aren't
    valid UTF-8 (the text is then decoded with replacement characters).
    """
    data = path.read_bytes()
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace"), None
    if b"\0" in data[:8192]:
        return None, "binary"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), "invalid"


def scan_text(path: Path, report: Report) -> bool:
    """Public-repo safety and writing-style checks. Returns False if the file was skipped as binary."""
    try:
        text, problem = load_text(path)
    except OSError as exc:
        report.error(path, 0, "can't read file: %s" % exc)
        return True
    if text is None:
        return False
    is_markdown = path.suffix.lower() == ".md"
    if problem == "invalid":
        flag = report.error if is_markdown else report.warn
        flag(path, 0, "not valid UTF-8. Scanned with replacement characters.")
    for number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                report.error(path, number, "looks like a secret (%s)" % label)
        for label, pattern in INTERNAL_PATTERNS:
            if pattern.search(line):
                report.error(path, number, "internal link or ID (%s), and this repo is public" % label)
        for match in UUID_RE.finditer(line):
            value = match.group(0).lower()
            if value in PLACEHOLDER_UUIDS or len(set(value.replace("-", ""))) == 1:
                continue
            report.error(path, number, "UUID (tenant, project or app ID?), and this repo is public")
        for label, pattern in WARN_PATTERNS:
            if pattern.search(line):
                report.warn(path, number, "%s" % label)
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
    return True


def check_catalog(agent_ids, report: Report) -> None:
    """Every agent needs a row in the README catalog table."""
    try:
        text = README.read_text(encoding="utf-8") if README.is_file() else ""
    except (OSError, UnicodeDecodeError) as exc:
        report.error(README, 0, "can't read the README to check the catalog: %s" % exc)
        return
    rows = [line for line in text.splitlines() if line.lstrip().startswith("|")]
    for agent_id in agent_ids:
        if not any("`%s`" % agent_id in row for row in rows):
            report.error(README, 0, "no catalog row for agent '%s'. Add a table row that mentions `%s`." % (agent_id, agent_id))


def repo_files():
    """Every file that could be committed: tracked files, plus untracked files git doesn't ignore."""
    try:
        listing = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-co", "--exclude-standard", "-z"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        found = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            found.extend(Path(dirpath) / filename for filename in filenames)
        return sorted(found)
    names = {name for name in listing.decode("utf-8", errors="replace").split("\0") if name}
    return sorted(path for path in (ROOT / name for name in names) if path.is_file())


def route(path: Path, report: Report) -> bool:
    """Say whether a file gets the agent checks. Also flags files that don't belong in the agents folder."""
    resolved = path.resolve()
    in_agents = AGENTS_DIR in resolved.parents
    if resolved.name.endswith(".agent.md"):
        if in_agents and resolved.parent != AGENTS_DIR:
            report.error(
                path,
                0,
                "keep agent files directly in .github/agents. A subfolder changes the agent ID and skips the catalog check.",
            )
        return True
    hidden = in_agents and any(part.startswith(".") for part in resolved.relative_to(AGENTS_DIR).parts)
    if in_agents and not hidden:
        if resolved.suffix.lower() == ".md":
            report.error(
                path,
                0,
                "Markdown files in .github/agents load as agents. Name it <id>.agent.md or move it out of that folder.",
            )
        else:
            report.warn(path, 0, "not an agent file. Only <id>.agent.md files belong in .github/agents.")
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate custom agent files.")
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="files to check. With none, checks everything in .github/agents, the README catalog and every file in the repo.",
    )
    args = parser.parse_args(argv)
    report = Report()
    agent_files = []

    if args.files:
        scan_files = []
        for path in args.files:
            if not path.is_file():
                report.error(path, 0, "file not found")
                continue
            scan_files.append(path)
            if route(path, report):
                agent_files.append(path)
    else:
        scan_files = repo_files()
        entries = sorted(AGENTS_DIR.rglob("*")) if AGENTS_DIR.is_dir() else []
        agent_files = [entry for entry in entries if entry.is_file() and route(entry, report)]
        if not agent_files:
            report.error(AGENTS_DIR, 0, "no *.agent.md files found")

    catalog_ids = []
    for path in agent_files:
        agent_id = check_agent(path, report)
        if agent_id and path.resolve().parent == AGENTS_DIR:
            catalog_ids.append(agent_id)
    skipped = sum(1 for path in scan_files if not scan_text(path, report))
    if catalog_ids:
        check_catalog(catalog_ids, report)

    print(
        "Checked %d agent file(s) and scanned %d file(s), skipped %d binary: %d error(s), %d warning(s)."
        % (len(agent_files), len(scan_files) - skipped, skipped, report.errors, report.warnings)
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
