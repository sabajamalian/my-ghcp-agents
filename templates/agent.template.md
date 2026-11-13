---
name: replace-with-agent-id
description: >-
  One or two sentences: what the agent does and when to use it. The app reads
  this text to decide when to delegate work to the agent.
tools:
  # Required. Least privilege: name every tool the agent needs and nothing else.
  # Built-in groups: read, search, edit, execute, web, agent, todo.
  # MCP tools use server/tool. The validator rejects * and server/*, which include write tools.
  # A name that doesn't resolve is dropped without a warning, so check the spelling.
  # execute and agent can't be restricted by this list. If you add them, put the limits in the prompt.
  - read
  - search
# Optional. Uncomment both to stop the app from handing work to this agent on its own.
# infer: false
# disable-model-invocation: true
---

You are <Name>. One sentence on what you do. One sentence on what you never do.

## Non-negotiables

The few rules that must hold on every run. Number them. Keep it under ten.

1. <Rule>
2. <Rule>

## Inputs

What you take from the user's message, and which items you may ask about. Ask only when a missing item would change the result.

## Workflow

The numbered steps, in order. Name the tools used at each step. Say when to stop.

## Output format

The exact shape of the reply, with a short example in a code block. Say what comes first.

## Safety rules

What the agent must never do. List write actions that are allowed and the confirmation each one needs. If the agent is read-only, say so.

## When something is unavailable

What to do when a tool or source is missing or signed out. Say what the reply must tell the user.

## Final checklist

The checks to run before replying.
