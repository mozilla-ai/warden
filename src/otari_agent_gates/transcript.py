"""Extract the current turn from a Claude Code session transcript.

Used by ``otari policy check``, which runs on the machine that holds the
transcript file: it reads the JSONL, extracts what the gates need, and sends only
that onward. A running gateway never reads the file itself.
"""

from __future__ import annotations

import json
import re
from typing import Any

_TRUNCATION_NOTE = "[... earlier tool output in this turn omitted for length ...]\n"

_HEREDOC_START_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")

# Constructs that hand quoted text to a shell for real execution. Deliberately short,
# not a shell parser: just the cases that must keep a quoted command visible to a gate.
_REEXEC_TRIGGER_RE = re.compile(r"\b(?:bash|sh|zsh|dash)\s+-c\b|\beval\b|\bssh\b|\bxargs\b")
# Escape-aware, so a JSON blob's own embedded `\"` does not end the match early.
_QUOTED_STRING_RE = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")

_EDIT_TOOL_PATH_FIELDS = {"Edit": "file_path", "Write": "file_path", "NotebookEdit": "notebook_path"}


def extract_excerpt(transcript_path: str, max_chars: int) -> str:
    """Render the current turn (since the last real user message) as compact text.

    Front-truncates when the rendered text exceeds ``max_chars``: the oldest events go
    first, the most recent survive. The gateway re-truncates to each judge gate's own
    cap regardless, so this only keeps the request small. That truncation is why a rule
    like "ran make lint" belongs on a ``command`` gate rather than a judge gate reading
    this excerpt: evidence from early in a long turn can fall outside the cap.
    """
    entries = _current_turn_entries(_read_jsonl(transcript_path))
    rendered = [text for text in (_render_entry(entry) for entry in entries) if text]
    text = "\n".join(rendered)
    if len(text) > max_chars:
        text = _TRUNCATION_NOTE + text[-max_chars:]
    return text


def extract_executed_commands(transcript_path: str) -> list[dict[str, Any]]:
    """Every Bash command the current turn actually ran, each paired with whether it errored.

    Parsed from the transcript's structured ``tool_use``/``tool_result`` blocks (matched by
    ``tool_use_id``), never from rendered prose, and with no character cap: this is a
    handful of dict comparisons, not something bounded by a model's context window. Each
    command is stripped of heredoc bodies, comments, and (conditionally) quoted data before
    being returned; see ``strip_inert_shell_regions``.
    """
    entries = _current_turn_entries(_read_jsonl(transcript_path))

    tool_use_commands: dict[str, str] = {}
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Bash"):
                continue
            tool_use_id = block.get("id")
            command = (block.get("input") or {}).get("command")
            if isinstance(tool_use_id, str) and isinstance(command, str):
                tool_use_commands[tool_use_id] = strip_inert_shell_regions(command)

    commands: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("type") != "user":
            continue
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                continue
            tool_use_id = block.get("tool_use_id")
            command = tool_use_commands.get(tool_use_id) if isinstance(tool_use_id, str) else None
            if command is None or _was_denied(block):
                continue
            commands.append({"command": command, "is_error": bool(block.get("is_error", False))})
    return commands


def _was_denied(tool_result: dict[str, Any]) -> bool:
    """Whether a ``tool_result`` records a PreToolUse denial rather than a run.

    A denied call never executed, so a ``must_not_run`` gate must not fail on it
    and a ``must_run_and_succeed`` gate must not count it. Claude Code reports
    the denial as the tool's result, prefixed with the hook event name.
    """
    text = _render_tool_result(tool_result.get("content"))
    return "PreToolUse" in text and ("permissionDecision" in text or "hook error" in text)


def strip_inert_shell_regions(command: str) -> str:
    """Strip heredoc bodies, unquoted comments, and (conditionally) quoted-string contents.

    Heredoc bodies and comments are never executed, so a banned phrase inside one is not
    evidence the command ran. Quoted text is usually inert data (a JSON blob, a ``curl -d``
    argument) but can be a real invocation (``bash -c "git push --force"``), so it is only
    masked on a line with none of the re-execution constructs in ``_REEXEC_TRIGGER_RE``.
    The trigger is checked per line, so one line's ``bash -c`` cannot unmask an unrelated
    JSON fixture on another line of the same command. A heredoc delimiter's own quotes are
    syntax, so the line opening a heredoc is never masked.
    """
    lines = command.split("\n")
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        no_comment = _strip_unquoted_comment(line)
        match = _HEREDOC_START_RE.search(line)
        if match is None and not _REEXEC_TRIGGER_RE.search(no_comment):
            no_comment = _QUOTED_STRING_RE.sub(lambda m: m.group(0)[0] * 2, no_comment)
        output.append(no_comment)
        if match is not None:
            delimiter = match.group(2)
            index += 1
            while index < len(lines) and lines[index].strip() != delimiter:
                index += 1
            # The terminator line carries no command text of its own, so it is skipped too.
        index += 1
    return "\n".join(output)


def _strip_unquoted_comment(line: str) -> str:
    in_single = False
    in_double = False
    for position, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:position]
    return line


def extract_edited_paths(transcript_path: str) -> list[str]:
    """Every file path the current turn's ``Edit``/``Write``/``NotebookEdit`` calls touched."""
    entries = _current_turn_entries(_read_jsonl(transcript_path))
    paths: list[str] = []
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                continue
            path_field = _EDIT_TOOL_PATH_FIELDS.get(block.get("name", ""))
            if path_field is None:
                continue
            path = (block.get("input") or {}).get(path_field)
            if isinstance(path, str) and path:
                paths.append(path)
    return paths


def extract_loaded_context_paths(transcript_path: str) -> list[str]:
    """Every path Claude Code injected as a ``nested_memory`` attachment, anywhere in the session.

    Not turn-scoped, unlike the other extractors: a directory's guidance is loaded once,
    the first time a file under it is touched, and does not recur every turn.
    """
    paths: list[str] = []
    for entry in _read_jsonl(transcript_path):
        attachment = entry.get("attachment")
        if isinstance(attachment, dict) and attachment.get("type") == "nested_memory":
            path = attachment.get("path")
            if isinstance(path, str) and path:
                paths.append(path)
    return paths


def latest_turn_id(transcript_path: str) -> str | None:
    """The most recent entry's ``uuid``, or ``None`` when the file is missing, empty, or has none.

    Two checks in one session's retry loop get different ids because a new entry (the fix)
    was appended between them, which is what makes each traceable to its point in the
    conversation.
    """
    entries = _read_jsonl(transcript_path)
    for entry in reversed(entries):
        uuid = entry.get("uuid")
        if isinstance(uuid, str) and uuid:
            return uuid
    return None


def _current_turn_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The current turn's own entries: everything since the last real user message."""
    turn_entries = [entry for entry in entries if entry.get("type") in ("user", "assistant")]
    if not turn_entries:
        return []
    start = 0
    for index in range(len(turn_entries) - 1, -1, -1):
        if _is_real_user_turn(turn_entries[index]):
            start = index
            break
    return turn_entries[start:]


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)
    except OSError:
        return []
    return entries


def _is_real_user_turn(entry: dict[str, Any]) -> bool:
    """True for an actual human message, false for a synthetic tool-result-carrying 'user' entry."""
    if entry.get("type") != "user":
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(isinstance(block, dict) and block.get("type") == "text" for block in content)
    return False


def _render_entry(entry: dict[str, Any]) -> str | None:
    message = entry.get("message") or {}
    role = message.get("role", entry.get("type", "unknown"))
    content = message.get("content")

    if isinstance(content, str):
        text = content.strip()
        return f"[{role}] {text}" if text else None

    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = str(block.get("text", "")).strip()
            if text:
                parts.append(text)
        elif block_type == "tool_use":
            tool_input = json.dumps(block.get("input", {}))[:500]
            parts.append(f"[tool_call: {block.get('name', '?')} input={tool_input}]")
        elif block_type == "tool_result":
            parts.append(f"[tool_result: {_render_tool_result(block.get('content'))}]")
    return f"[{role}] " + " ".join(parts) if parts else None


def _render_tool_result(content: Any) -> str:
    if isinstance(content, list):
        text = " ".join(
            str(block.get("text", "")) for block in content if isinstance(block, dict) and block.get("type") == "text"
        )
    else:
        text = str(content) if content is not None else ""
    text = text.strip()[:500]
    return text or "(non-text output)"
