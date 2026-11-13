---
applyTo: ".github/agents/**,templates/**"
---
# Agent files

- One agent per file: `.github/agents/<id>.agent.md`. The `name` field equals the file name without `.agent.md`. Put nothing else in that folder, because a stray `.md` file loads as an agent.
- `tools` is required. Name each tool and give the agent the least privilege it needs. `*` and `server/*` are errors, because they pull in write tools. A tool name that doesn't resolve is dropped without a warning.
- A tool list can't restrict the shell (`execute`) or subagents (`agent`). If an agent has either, its prompt carries the read-only rules and its doc page says the tool list doesn't enforce them.
- An agent that launches subagents or sessions sets `infer: false` and `disable-model-invocation: true`.
- A prompt must never let the agent claim a check it didn't run. It reports what it requested and what it confirmed.
- This repo is public. Never commit internal URLs, IDs, customer names, tokens or text copied from internal sources. Name tools and servers only.
- Write prose in a plain, direct voice. No emojis, no em or en dashes.
- Start from `templates/agent.template.md` and follow `docs/adding-an-agent.md`.
- Add a row for the agent to the catalog table in `README.md`. The row mentions the agent id in backticks.
- Run `python3 scripts/validate_agents.py` before you commit. It must report no errors.
