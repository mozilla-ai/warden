"""Unit tests for `otari_agent_gates.transcript`: current-turn extraction from a Claude Code JSONL transcript."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from otari_agent_gates import transcript as claude_transcript


def _write_transcript(tmp_path: Path, entries: list[dict[str, Any]]) -> str:
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(json.dumps(entry) for entry in entries), encoding="utf-8")
    return str(path)


def test_extract_excerpt_starts_at_last_real_user_turn(tmp_path: Path) -> None:
    entries: list[dict[str, Any]] = [
        {"type": "summary", "summary": "unrelated old turn"},
        {"type": "user", "message": {"role": "user", "content": "do the thing"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "working on it"},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}},
                ],
            },
        },
        {
            "type": "user",
            "message": {"role": "user", "content": [{"type": "tool_result", "content": "1 passed"}]},
        },
    ]
    excerpt = claude_transcript.extract_excerpt(_write_transcript(tmp_path, entries), max_chars=20_000)
    assert "do the thing" in excerpt
    assert "tool_call: Bash" in excerpt
    assert "tool_result: 1 passed" in excerpt
    assert "unrelated old turn" not in excerpt


def test_extract_excerpt_front_truncates_when_over_cap(tmp_path: Path) -> None:
    entries = [
        {"type": "user", "message": {"role": "user", "content": "go"}},
        {"type": "assistant", "message": {"role": "assistant", "content": "x" * 100}},
    ]
    excerpt = claude_transcript.extract_excerpt(_write_transcript(tmp_path, entries), max_chars=10)
    assert excerpt.startswith(claude_transcript._TRUNCATION_NOTE)
    assert excerpt.endswith("x" * 10)


def test_extract_excerpt_missing_file_returns_empty() -> None:
    assert claude_transcript.extract_excerpt("/nonexistent/path.jsonl", max_chars=100) == ""


def test_latest_turn_id_returns_the_last_entrys_uuid(tmp_path: Path) -> None:
    entries: list[dict[str, Any]] = [
        {"type": "user", "message": {"role": "user", "content": "go"}, "uuid": "first"},
        {"type": "assistant", "message": {"role": "assistant", "content": "ok"}, "uuid": "second"},
    ]
    assert claude_transcript.latest_turn_id(_write_transcript(tmp_path, entries)) == "second"


def test_latest_turn_id_missing_file_returns_none() -> None:
    assert claude_transcript.latest_turn_id("/nonexistent/path.jsonl") is None


def test_latest_turn_id_no_uuid_field_returns_none(tmp_path: Path) -> None:
    entries = [{"type": "user", "message": {"role": "user", "content": "go"}}]
    assert claude_transcript.latest_turn_id(_write_transcript(tmp_path, entries)) is None


def _bash_tool_use(tool_use_id: str, command: str) -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_use_id, "name": "Bash", "input": {"command": command}}],
        },
    }


def _tool_result(tool_use_id: str, *, is_error: bool) -> dict[str, Any]:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": "output", "is_error": is_error}],
        },
    }


def test_extract_executed_commands_pairs_tool_use_with_its_result(tmp_path: Path) -> None:
    entries: list[dict[str, Any]] = [
        {"type": "user", "message": {"role": "user", "content": "do the thing"}},
        _bash_tool_use("t1", "make lint"),
        _tool_result("t1", is_error=False),
    ]
    commands = claude_transcript.extract_executed_commands(_write_transcript(tmp_path, entries))
    assert commands == [{"command": "make lint", "is_error": False}]


def test_extract_executed_commands_records_an_error(tmp_path: Path) -> None:
    entries: list[dict[str, Any]] = [
        {"type": "user", "message": {"role": "user", "content": "do the thing"}},
        _bash_tool_use("t1", "make lint"),
        _tool_result("t1", is_error=True),
    ]
    commands = claude_transcript.extract_executed_commands(_write_transcript(tmp_path, entries))
    assert commands == [{"command": "make lint", "is_error": True}]


def test_extract_executed_commands_ignores_non_bash_tools(tmp_path: Path) -> None:
    entries: list[dict[str, Any]] = [
        {"type": "user", "message": {"role": "user", "content": "do the thing"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "x.py"}}],
            },
        },
        _tool_result("t1", is_error=False),
    ]
    assert claude_transcript.extract_executed_commands(_write_transcript(tmp_path, entries)) == []


def test_extract_executed_commands_ignores_commands_before_the_current_turn(tmp_path: Path) -> None:
    entries: list[dict[str, Any]] = [
        {"type": "user", "message": {"role": "user", "content": "old turn"}},
        _bash_tool_use("old", "make lint"),
        _tool_result("old", is_error=False),
        {"type": "user", "message": {"role": "user", "content": "new turn"}},
        _bash_tool_use("new", "pytest"),
        _tool_result("new", is_error=False),
    ]
    commands = claude_transcript.extract_executed_commands(_write_transcript(tmp_path, entries))
    assert commands == [{"command": "pytest", "is_error": False}]


def test_extract_executed_commands_missing_file_returns_empty() -> None:
    assert claude_transcript.extract_executed_commands("/nonexistent/path.jsonl") == []


def test_extract_executed_commands_strips_a_heredoc_body_containing_a_banned_phrase(
    tmp_path: Path,
) -> None:
    """A heredoc body is data being written to a file, not a command being run - a command
    gate matching `git push --force` must not trip on a test fixture that merely mentions
    it (the exact false positive this test guards against)."""
    command = (
        "cat > /tmp/plan.md << 'EOF'\nNever run `git push --force` under any circumstances.\nEOF\ncat /tmp/plan.md"
    )
    entries: list[dict[str, Any]] = [
        {"type": "user", "message": {"role": "user", "content": "go"}},
        _bash_tool_use("t1", command),
        _tool_result("t1", is_error=False),
    ]
    commands = claude_transcript.extract_executed_commands(_write_transcript(tmp_path, entries))
    assert "git push --force" not in commands[0]["command"]


def teststrip_inert_shell_regions_removes_heredoc_body() -> None:
    command = "cat > file.md << 'EOF'\nsome banned text\nEOF\necho done"
    stripped = claude_transcript.strip_inert_shell_regions(command)
    assert "some banned text" not in stripped
    assert "cat > file.md << 'EOF'" in stripped
    assert "echo done" in stripped


def teststrip_inert_shell_regions_removes_unquoted_heredoc_body() -> None:
    command = "cat > file.md << EOF\nbanned\nEOF"
    assert "banned" not in claude_transcript.strip_inert_shell_regions(command)


def teststrip_inert_shell_regions_handles_dash_heredoc() -> None:
    command = "cat > file.md <<- EOF\nbanned\nEOF"
    assert "banned" not in claude_transcript.strip_inert_shell_regions(command)


def teststrip_inert_shell_regions_leaves_a_real_invocation_alone() -> None:
    command = "git push --force origin main"
    assert claude_transcript.strip_inert_shell_regions(command) == command


def teststrip_inert_shell_regions_leaves_quoted_arguments_alone_for_a_real_reexec() -> None:
    """Deliberate: a quoted string can be a real invocation via `bash -c`/`ssh`/`eval`/
    `xargs`, so quoted text stays intact whenever one of those constructs is present."""
    for command in ['bash -c "git push --force"', 'ssh host "git push --force"']:
        assert claude_transcript.strip_inert_shell_regions(command) == command


def teststrip_inert_shell_regions_masks_quoted_data_with_no_reexec_construct() -> None:
    """The other side of the same tradeoff: a quoted string that is just data passed to an
    ordinary program (no bash -c/ssh/eval/xargs anywhere in the command) is not a real
    invocation, so its content is masked - the exact shape of a JSON test fixture that
    merely contains a banned phrase as a field value, never runs it."""
    command = 'my-script.py "{\\"command\\": \\"git push --force origin main\\"}"'
    stripped = claude_transcript.strip_inert_shell_regions(command)
    assert "git push --force" not in stripped


def teststrip_inert_shell_regions_scopes_the_reexec_trigger_per_line() -> None:
    """Regression test for a real false positive: a multi-line command with an unrelated
    `bash -c "..."` on one line must not disable masking on a *different* line's own quoted
    JSON fixture - the trigger check used to be scoped to the whole command, so any line's
    trigger word leaked into every other line, unmasking a fixture two lines away that had
    nothing to do with it."""
    command = (
        'run "{\\"command\\": \\"git push --force origin main\\"}"\n'
        'echo "for reference: bash -c \\"real invocations\\" still get caught"'
    )
    stripped = claude_transcript.strip_inert_shell_regions(command)
    first_line, second_line = stripped.split("\n")
    assert "git push --force" not in first_line
    assert "bash -c" in second_line


def teststrip_inert_shell_regions_masks_single_quoted_data_too() -> None:
    command = "my-script.py 'git push --force origin main'"
    assert "git push --force" not in claude_transcript.strip_inert_shell_regions(command)


def teststrip_inert_shell_regions_does_not_mask_a_heredoc_delimiters_own_quotes() -> None:
    """A heredoc delimiter's quotes (`<< 'EOF'`) are syntax Bash reads to find the body's
    end, not data - masking them would corrupt the marker, not just hide inert text."""
    command = "cat > file.md << 'EOF'\nsome banned text\nEOF\necho done"
    stripped = claude_transcript.strip_inert_shell_regions(command)
    assert "cat > file.md << 'EOF'" in stripped


def test_strip_unquoted_comment_strips_from_an_unquoted_hash() -> None:
    assert claude_transcript._strip_unquoted_comment("echo hi # a comment") == "echo hi "


def test_strip_unquoted_comment_ignores_a_hash_inside_quotes() -> None:
    line = 'echo "a # not a comment"'
    assert claude_transcript._strip_unquoted_comment(line) == line


def _edit_tool_use(tool_name: str, path_field: str, path: str) -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "t1", "name": tool_name, "input": {path_field: path}}],
        },
    }


def test_extract_edited_paths_collects_edit_write_and_notebook_edit(tmp_path: Path) -> None:
    entries: list[dict[str, Any]] = [
        {"type": "user", "message": {"role": "user", "content": "do the thing"}},
        _edit_tool_use("Edit", "file_path", "/repo/a.py"),
        _edit_tool_use("Write", "file_path", "/repo/b.py"),
        _edit_tool_use("NotebookEdit", "notebook_path", "/repo/c.ipynb"),
        _edit_tool_use("Read", "file_path", "/repo/d.py"),
    ]
    paths = claude_transcript.extract_edited_paths(_write_transcript(tmp_path, entries))
    assert paths == ["/repo/a.py", "/repo/b.py", "/repo/c.ipynb"]


def test_extract_edited_paths_ignores_edits_before_the_current_turn(tmp_path: Path) -> None:
    entries: list[dict[str, Any]] = [
        {"type": "user", "message": {"role": "user", "content": "old turn"}},
        _edit_tool_use("Edit", "file_path", "/repo/old.py"),
        {"type": "user", "message": {"role": "user", "content": "new turn"}},
        _edit_tool_use("Edit", "file_path", "/repo/new.py"),
    ]
    paths = claude_transcript.extract_edited_paths(_write_transcript(tmp_path, entries))
    assert paths == ["/repo/new.py"]


def test_extract_loaded_context_paths_collects_nested_memory_attachments(tmp_path: Path) -> None:
    entries: list[dict[str, Any]] = [
        {"type": "attachment", "attachment": {"type": "nested_memory", "path": "/repo/web/AGENTS.md"}},
        {"type": "user", "message": {"role": "user", "content": "go"}},
        {"type": "attachment", "attachment": {"type": "other_kind", "path": "/repo/ignored.md"}},
    ]
    paths = claude_transcript.extract_loaded_context_paths(_write_transcript(tmp_path, entries))
    assert paths == ["/repo/web/AGENTS.md"]


def test_extract_loaded_context_paths_is_not_scoped_to_the_current_turn(tmp_path: Path) -> None:
    """Unlike `extract_edited_paths`, a load from many turns ago still counts - Claude Code's
    own nested_memory injection does not necessarily recur every turn."""
    entries: list[dict[str, Any]] = [
        {"type": "attachment", "attachment": {"type": "nested_memory", "path": "/repo/web/AGENTS.md"}},
        {"type": "user", "message": {"role": "user", "content": "an old turn"}},
        {"type": "user", "message": {"role": "user", "content": "the current turn"}},
        _edit_tool_use("Edit", "file_path", "/repo/web/src/x.tsx"),
    ]
    paths = claude_transcript.extract_loaded_context_paths(_write_transcript(tmp_path, entries))
    assert paths == ["/repo/web/AGENTS.md"]


def test_extract_loaded_context_paths_missing_file_returns_empty() -> None:
    assert claude_transcript.extract_loaded_context_paths("/nonexistent/path.jsonl") == []
