# Adding an agent

Each agent is one file in `.github/agents/`. The GitHub Copilot desktop app and Copilot CLI load it in sessions opened on this repo.

## Steps

1. Copy `templates/agent.template.md` to `.github/agents/<id>.agent.md`. The id is lowercase words joined by hyphens, like `tech-researcher`.
2. Set `name` to the id. It must match the file name.
3. Write the `description`. The app uses it to decide when to hand work to the agent, so say what the agent does and when to pick it.
4. List `tools` explicitly. Start with `read` and `search`, then add only what the agent needs. MCP tools use the form `server/tool`.
5. Fill in the prompt sections. The hard limit is 30,000 characters. Aim for under 12,000.
6. Add a row to the catalog table in `README.md`. Add a page under `docs/` if the agent needs setup notes.
7. Run `python3 scripts/validate_agents.py`. It must report no errors.
8. Test the agent in a session (see Testing).

## Conventions

- **The repo is public.** No internal URLs, IDs, customer names, tokens or text copied from internal sources. Name tools and servers only. The validator blocks the common patterns but can't catch everything, so read your diff.
- **Read-only by default.** If an agent writes anything, its prompt must say what it may write and what confirmation each write needs.
- **No hard-coded model versions or project IDs.** Look them up when the agent runs. `tech-researcher` finds the llm-assist project through `list_repositories` and reads the available models from the `task` tool.
- **Prompt structure.** Role, non-negotiables, inputs, workflow, output format, safety rules, what to do when a tool is unavailable, final checklist. Drop the sections that don't apply.
- **Voice.** Plain and direct. No emojis and no em or en dashes. The validator checks both.

## Testing

Start a session on this repo, pick the agent, and ask two questions:

1. A question with a known answer. The agent should answer it and back each claim with a source you can open.
2. A question built on a false premise, such as a flag or setting that doesn't exist. The agent should say it found no evidence, not play along.

`docs/tech-researcher.md` has worked examples.

## Sharing pieces between agents

Keep each agent self-contained until a second agent needs the same piece, such as the reference format or the review protocol. Then move that piece into a skill at `.github/skills/<skill-name>/SKILL.md` and have both agents use it. Don't build shared skills before there's a second user.

## Not built yet

- Shared skills
- Plugin or marketplace packaging
- An install script for `~/.copilot/agents`
- CI that runs the validator
- Automated prompt tests
