# Cursor SDK for Evidence and Explanation only

The challenge needs an agent, and the hard requirement is that every agent call uses the Cursor Python SDK. We will not use the SDK for arithmetic or for writing `output.csv`. Image Amount Extraction, Message Interpretation, and Explanation are one-shot `Agent.prompt` calls on a local sandbox `cwd`; a deterministic engine owns the Decision, and the Writer persists it. A single durable agent per Request, or a repo-rooted agent, would leak other users, future Exchange Rates, and Evidence-stage scratch into the Decision.
