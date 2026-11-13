# Adding an agent

Each agent is one file in `.github/agents/`. The GitHub Copilot desktop app and Copilot CLI load it in sessions opened on this repo.

## Steps

1. Copy `templates/agent.template.md` to `.github/agents/<id>.agent.md`. The id is lowercase words joined by hyphens, like `tech-researcher`.
2. Set `name` to the id. It must match the file name.
3. Write the `description`. The app uses it to decide when to hand work to the agent, so say what the agent does and when to pick it.
4. List `tools` explicitly. Start with `read` and `search`, then add only what the agent needs. MCP tools use the form `server/tool`. See Tools below.
5. Fill in the prompt sections. The hard limit is 30,000 characters. Stay well under it.
6. Add a row to the catalog table in `README.md`. Add a page under `docs/` if the agent needs setup notes.
7. Run `python3 scripts/validate_agents.py`. It must report no errors.
8. Test the agent in a session (see Testing).

## Conventions

- **The repo is public.** No internal URLs, IDs, customer names, tokens or text copied from internal sources. Name tools and servers only. The validator blocks the common patterns but can't catch everything, so read your diff.
- **Read-only by default.** If an agent writes anything, its prompt must say what it may write and what confirmation each write needs. If it can't be held to read-only by its tool list (it has `execute`, `agent` or `create_session`), the prompt and the doc page say so.
- **No hard-coded model versions or project IDs.** Look them up when the agent runs. `tech-researcher` finds the llm-assist project through `list_repositories` and reads the available models from the `task` tool.
- **Prompt structure.** Role, non-negotiables, inputs, workflow, output format, safety rules, what to do when a tool is unavailable, final checklist. Drop the sections that don't apply.
- **Voice.** Plain and direct. No emojis and no em or en dashes. The validator checks both.

## Tools

- `tools` is required, and the validator rejects a missing or empty list. An agent with no `tools` key gets every tool.
- Name each tool. `*` and `server/*` are errors, because they pull in write tools. If an agent really needs a wildcard, change the validator in the same pull request and say why in the description.
- A name that doesn't resolve is dropped without a warning. When a source shows as unavailable, check the spelling and the server key (Customize > Installed) before anything else.
- Built-in groups are `read`, `search`, `edit`, `execute`, `web`, `agent` and `todo`.
- A tool list can't restrict what the shell (`execute`) or a subagent (`agent`) does. An agent that has either carries its read-only rules in the prompt, and its doc page says that the tool list doesn't enforce them. The validator prints an INFO line naming the write-capable tools on every run, so read it.
- Agents that launch subagents or sessions set `infer: false` and `disable-model-invocation: true`, so the app doesn't hand them work on its own.

## Validator

`python3 scripts/validate_agents.py` needs Python 3 and nothing else. With no arguments it checks the whole repo. With file paths it checks only those files.

- **Front matter.** It reads a small YAML subset: one-line strings (quoted or plain), `true` and `false`, inline lists like `[read, search]`, `- ` lists, and `>-` or `|` text blocks. Anchors, tags, inline maps and `null` are errors, because another parser could read them differently. An unknown key is an error, with a suggestion when it looks like a typo. A plain value that contains `: ` needs quotes or a `>-` block.
- **Agent files.** The name must match the file name, `description` and the prompt must be non-empty, and the prompt must stay under 30,000 characters. Only `*.agent.md` files belong in `.github/agents/`: a stray `.md` file there loads as an agent, so the validator flags it.
- **Every file.** It scans tracked files and untracked files that git doesn't ignore. It flags secrets, internal links, UUIDs and email addresses. In Markdown it also flags emojis, em and en dashes, and filler phrases.
- **Catalog.** Every agent id must appear in backticks in a row of the `README.md` table.

## Testing

Start a session on this repo, pick the agent, and ask two questions:

1. A question with a known answer. The agent should answer it and back each claim with a source you can open.
2. A question built on a false premise, such as a flag or setting that doesn't exist. The agent should say it found no evidence, not play along.

`docs/tech-researcher.md` has test prompts.

## Sharing pieces between agents

Keep each agent self-contained until a second agent needs the same piece, such as the reference format or the review protocol. Then move that piece into a skill at `.github/skills/<skill-name>/SKILL.md` and have both agents use it. Don't build shared skills before there's a second user.

## Not built yet

- Shared skills
- Plugin or marketplace packaging
- An install script for `~/.copilot/agents`
- CI that runs the validator
- Automated prompt tests
