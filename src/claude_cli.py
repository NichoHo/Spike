"""
Spike: Claude via the `claude -p` CLI on the user's Pro plan (Blueprint §6.7).
Used only for the creator profile, the editor pass and "Ask the editor". Everything else stays on Gemini.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src import claude_fallback
from src.db import add_claude_usage, log_event

CLAUDE_TIMEOUT_S = 600  # a 12k-character editor prompt took about 170 s


# Without this first line a long task prompt makes the model answer in prose, and the CLI then prints plain
# text instead of the JSON envelope (seen with the editor prompt). A short JSON-only system prompt works.
JSON_ONLY = "You output JSON only, matching the provided schema. Never write prose or code fences.\n\n"


class ClaudeError(RuntimeError):
    """The CLI failed, hit a plan limit, or returned no structured output."""


def _claude_exe() -> str:
    """Path of the real claude binary. The npm shim (claude.CMD) runs through cmd.exe, which cuts every
    argument at its first newline, so a multi-line --system-prompt would silently lose its rules."""
    exe = shutil.which("claude")
    if not exe:
        raise ClaudeError("claude CLI not found on PATH")
    if exe.lower().endswith((".cmd", ".bat")):
        real = Path(exe).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if real.exists():
            return str(real)
        print("  [claude] Warning: only the .cmd shim was found; multi-line prompts may be cut at the first newline.")
    return exe


def require_all(schema: Any) -> Any:
    """Mark every property of every object in a Pydantic JSON schema as required. Defaults would let the
    model answer with {} or leave whole lists out."""
    if isinstance(schema, dict):
        if isinstance(schema.get("properties"), dict):
            schema["required"] = list(schema["properties"])
        for v in schema.values():
            require_all(v)
    elif isinstance(schema, list):
        for v in schema:
            require_all(v)
    return schema


def run_claude(
    system: str,
    prompt: str,
    schema: Union[str, Dict[str, Any]],
    video_id: Optional[int] = None,
    label: str = "",
    model: str = "sonnet",
    images: Optional[List[bytes]] = None,
) -> Dict[str, Any]:
    """One non-interactive Claude call. Returns the structured JSON dict; callers validate it with Pydantic.

    Not --bare: that skips the OAuth login, so it cannot use the Pro plan. Instead user settings, MCP servers
    and skills are switched off (input drops from ~34k to ~4k tokens, measured) and the call runs from an
    empty folder so no project CLAUDE.md is picked up.
    """
    if claude_fallback.paused():
        raise ClaudeError("Claude is paused (sidebar)")
    exe = _claude_exe()
    if images:  # the model views them with the Read tool: f0.jpg, f1.jpg ... in the call's working folder
        prompt = "Image files in the working folder: " + ", ".join(f"f{i}.jpg" for i in range(len(images))) + ". Read each one first.\n\n" + prompt
    schema_json = schema if isinstance(schema, str) else json.dumps(schema)
    cmd = [
        exe, "-p", "--model", model,
        "--system-prompt", JSON_ONLY + system,
        "--tools", "Read" if images else "",
        *(["--allowedTools", "Read"] if images else []),  # without this -p mode denies the Read
        "--setting-sources", "project",
        "--strict-mcp-config", "--disable-slash-commands",
        "--output-format", "json",
        "--json-schema", schema_json,
        "--no-session-persistence",
    ]
    def attempt(extra: str) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory() as empty_dir:
            for i, img in enumerate(images or []):
                (Path(empty_dir) / f"f{i}.jpg").write_bytes(img)
            try:
                res = subprocess.run(
                    cmd, input=prompt + extra, capture_output=True, text=True, encoding="utf-8",
                    cwd=empty_dir, timeout=CLAUDE_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired as e:
                raise ClaudeError(f"claude timed out after {CLAUDE_TIMEOUT_S}s") from e
        if res.returncode != 0:
            raise ClaudeError(f"claude exited {res.returncode}: {(res.stderr or res.stdout).strip()[:300]}")
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise ClaudeError(f"claude returned non-JSON output: {res.stdout[:200]}") from e

    # Structured output is not guaranteed: on a long prompt the model sometimes answers in prose. Retry once.
    retry_note = "\n\nReply ONLY with the structured JSON output. Do not write any prose."
    claude_fallback.mark_running(label or "call", 2 * CLAUDE_TIMEOUT_S)
    try:
        out = attempt("")
        if not isinstance(out.get("structured_output"), dict):
            out = attempt(retry_note)
    except ClaudeError as first:
        if "non-JSON" not in str(first):
            raise
        out = attempt(retry_note)
    finally:
        claude_fallback.clear_running()

    usage = out.get("usage", {})
    tokens_in = (usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
                 + usage.get("cache_read_input_tokens", 0))
    try:
        log_event(
            "info",
            f"claude {label or 'call'}: in={tokens_in} out={usage.get('output_tokens', 0)} cost_usd={out.get('total_cost_usd')}",
            video_id,
        )
        add_claude_usage(label or "call", tokens_in, usage.get("output_tokens", 0), out.get("total_cost_usd"), video_id)
    except Exception:
        pass  # usage logging must never fail the call
    if tokens_in > 40000:
        print(f"  [claude] Warning: {tokens_in} input tokens; check that hooks/CLAUDE.md are not being loaded.")

    if out.get("is_error") or not isinstance(out.get("structured_output"), dict):
        raise ClaudeError(f"claude gave no structured output: {str(out.get('result'))[:200]}")
    return out["structured_output"]
