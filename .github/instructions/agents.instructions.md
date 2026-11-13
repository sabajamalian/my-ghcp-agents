---
applyTo: ".github/agents/**,templates/**"
---
# Agent files

- One agent per file: `.github/agents/<id>.agent.md`. The `name` field equals the file name without `.agent.md`.
- List `tools` explicitly, with the least privilege the agent needs. Avoid `*` and `server/*` wildcards, which pull in write tools.
- This repo is public. Never commit internal URLs, IDs, customer names, tokens or text copied from internal sources. Name tools and servers only.
- Write prose in a plain, direct voice. No emojis, no em or en dashes.
- Start from `templates/agent.template.md` and follow `docs/adding-an-agent.md`.
- Add a row for the agent to the catalog table in `README.md`.
- Run `python3 scripts/validate_agents.py` before you commit. It must report no errors.
