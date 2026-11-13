# my-ghcp-agents
My personal custom agents to run on GHCP for my own tasks

## Agents

| Agent | What it does | Needs | Status |
|---|---|---|---|
| [`tech-researcher`](docs/tech-researcher.md) | Answers a technical question with numbered references, after review by other model families. Doesn't edit files, post messages or change records. | Optional sign-ins: WorkIQ, Slack, MSX, and the llm-assist project | v1 |

## Use an agent

1. Open this repo in the GitHub Copilot desktop app and start a session.
2. Pick the agent in the agent picker in the prompt box, or type `/agent`.
3. Ask your question.

Agents load in sessions opened on this repo. To use one in another project, copy its file to `~/.copilot/agents/`, or run `/add-dir` on this repo's path in that session. Both load the agent as trusted configuration, so read an agent file before you do either.

## Add an agent

Copy `templates/agent.template.md` and follow [docs/adding-an-agent.md](docs/adding-an-agent.md). Run `python3 scripts/validate_agents.py` before you commit.
