"""The Claude CLI backend, hardened as in AMENDMENTS-v3 C8 and experiment_A.frozen.yaml.

Every call runs in a fresh empty temporary directory with no tools, no MCP servers, no setting
sources, the agent system prompt replaced, and auto-update disabled. The structural checks are
evaluated on every call; the runner aborts on the first violation.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

SYSTEM_PROMPT = "You are a helpful assistant."
USAGE_LIMIT = re.compile(r"(usage|rate|spend|session|weekly|monthly)[ _-]?limit|limit (reached|exceeded)"
                         r"|hit your .{0,40}limit|out of (extra )?usage|resets? (at|in)\b|quota", re.I)


class UsageLimit(Exception):
    """The subscription blocked the call. Not a model call: no row is written."""


def cli_version():
    out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=60)
    return out.stdout.strip().split()[0]


def command(model, effort="low", thinking="default"):
    """thinking="disabled" passes alwaysThinkingEnabled=false explicitly, since --setting-sources ""
    loads no settings file; the runner also sets MAX_THINKING_TOKENS=0 (see env())."""
    cmd = ["claude", "-p", "--input-format", "text", "--output-format", "stream-json",
           "--verbose", "--model", model]
    if effort:
        cmd += ["--effort", effort]
    cmd += ["--tools", "", "--permission-mode", "dontAsk", "--strict-mcp-config",
            "--setting-sources", "", "--disable-slash-commands", "--system-prompt", SYSTEM_PROMPT]
    if thinking == "disabled":
        cmd += ["--settings", json.dumps({"alwaysThinkingEnabled": False})]
    return cmd


def env(thinking="default"):
    e = dict(os.environ, DISABLE_AUTOUPDATER="1")
    if thinking == "disabled":
        e["MAX_THINKING_TOKENS"] = "0"
    return e


def _transcript_models(session_id, wait_s=5.0):
    """Model ids of the assistant turns in the session transcript, or None if not found."""
    deadline = time.time() + wait_s
    while time.time() < deadline:
        files = glob.glob(str(Path.home() / ".claude/projects/*" / f"{session_id}.jsonl"))
        if files:
            models = []
            for line in open(files[0]):
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("type") == "assistant":
                    models.append((o.get("message") or {}).get("model"))
            if models:
                return models
        time.sleep(0.5)
    return None


class CliBackend:
    name = "claude_cli"

    def __init__(self, model, effort="low", thinking="default"):
        self.model, self.effort, self.thinking = model, effort, thinking
        self.version = cli_version()

    def call(self, prompt, timeout_s):
        workdir = tempfile.mkdtemp(prefix="expA-call-")
        t0 = time.time()
        try:
            proc = subprocess.run(command(self.model, self.effort, self.thinking), input=prompt,
                                  capture_output=True, text=True, timeout=timeout_s, cwd=workdir,
                                  env=env(self.thinking))
        except subprocess.TimeoutExpired:
            return {"outcome_hint": "timeout", "text": "", "latency_ms": int(timeout_s * 1000),
                    "structural_violations": [], "stderr": ""}
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        latency = int((time.time() - t0) * 1000)
        init, assistants, result = None, [], None
        for line in proc.stdout.splitlines():
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("type") == "system" and o.get("subtype") == "init":
                init = o
            elif o.get("type") == "assistant":
                assistants.append(o.get("message") or {})
            elif o.get("type") == "result":
                result = o
        text = (result or {}).get("result") or ""
        if (result is None or result.get("is_error")) and (
                USAGE_LIMIT.search(text) or USAGE_LIMIT.search(proc.stderr or "")):
            raise UsageLimit(text or proc.stderr)
        if result is None or result.get("is_error"):
            return {"outcome_hint": "api_error", "text": text, "latency_ms": latency,
                    "structural_violations": [], "stderr": (proc.stderr or "")[-2000:]}

        violations = []
        if init is None:
            violations.append("no init event")
        else:
            if init.get("tools"):
                violations.append(f"tools listed: {init.get('tools')}")
            if init.get("mcp_servers"):
                violations.append(f"mcp servers listed: {init.get('mcp_servers')}")
            if init.get("model") != self.model:
                violations.append(f"init model {init.get('model')} != {self.model}")
            if init.get("claude_code_version") and init["claude_code_version"] != self.version:
                violations.append(f"cli version {init['claude_code_version']} != {self.version}")
        if result.get("num_turns") != 1:
            violations.append(f"num_turns {result.get('num_turns')}")
        for m in assistants:
            if m.get("model") and m["model"] != self.model:
                violations.append(f"assistant model {m['model']} != {self.model}")
            for block in m.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    violations.append("tool_use block")
                if (self.thinking == "disabled" and isinstance(block, dict)
                        and block.get("type") in ("thinking", "redacted_thinking")):
                    violations.append("thinking block with thinking disabled")
        tmodels = _transcript_models(init.get("session_id")) if init else None
        if tmodels is None:
            violations.append("session transcript not found")
        elif any(m != self.model for m in tmodels if m):
            violations.append(f"transcript models {sorted(set(tmodels))} != {self.model}")

        usage = result.get("usage") or {}
        stop = result.get("stop_reason")
        return {"outcome_hint": "max_tokens" if stop == "max_tokens" else None,
                "text": text, "model_id": init.get("model") if init else None,
                "stop_reason": stop, "num_turns": result.get("num_turns"),
                "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
                "latency_ms": latency, "cost_usd": result.get("total_cost_usd"),
                "session_id": init.get("session_id") if init else None,
                "structural_violations": violations, "stderr": ""}
