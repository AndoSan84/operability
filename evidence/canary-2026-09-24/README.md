# CLI canary, 2026-09-24 (evidence for AMENDMENTS-v3 C8)

One call, Claude Code 2.1.281, model `claude-sonnet-5`, fresh empty temporary directory, flags:
`-p --input-format stream-json --output-format stream-json --verbose --model claude-sonnet-5
--tools "" --system-prompt "You are a helpful assistant." --strict-mcp-config --setting-sources ""
--disable-slash-commands --permission-mode dontAsk`.

Input: a user turn, a harness-built assistant turn containing a secret word, a user turn asking
for the word and for the tools available.

What it shows:

- `tools: []`, `mcp_servers: []`, `permissionMode: dontAsk`, model `claude-sonnet-5` in the init
  event and in the transcript; the model answers `NONE` for tools.
- The system prompt is replaced, but an agent-identity prefix remains
  (`"cliPrefix": "You are a Claude agent, built on Anthropic's Claude Agent SDK."`).
- The CLI injects attachments regardless of flags: working environment, model identity and
  knowledge cutoff, a token-budget reminder, the date, account context (e-mail, organisation id:
  redacted here). Input tokens: 578 for two short turns.
- The harness-built assistant turn is **not** delivered as a turn in place: it is written before
  the first user turn, and the model then generates its own assistant turn (17 output tokens)
  reproducing it. Two model calls instead of one. For a long cell-specific content the regenerated
  turn need not match the harness content byte for byte, which would break the strip. Hence
  `model.context_rendering: inline`.

E-mail, organisation UUIDs and temporary paths are redacted; nothing else is edited.
