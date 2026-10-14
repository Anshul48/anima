# Builder authority boundary — user private information

Status: DEFINITIVE. This note constrains the builder (the agent or developer
implementing Entorhinal in this project), not the product's end user.

## Rule

Building Entorhinal does not grant the builder any authority to access,
inspect, read, copy, or analyze the user's private information that
Entorhinal tracks, stores, or analyzes.

- The builder works only with explicitly provided inputs: the repository,
  authorized synthetic or user-supplied task episodes (e.g. the
  `entorhinal.dev-task.01` development episodes), and user-pasted context.
- Live user data captured by a running Entorhinal instance — task streams,
  stored evidence, timelines, packets, exports, or any other tracked content
  belonging to the user — is outside the builder's authority unless the user
  explicitly grants access to a specific item for a specific purpose.
- Debugging, verification, and evaluation must use synthetic, user-provided,
  or properly consented data. A diagnostic need never implies access to
  private user data.
- This boundary survives convenience: if private data would make a task
  easier, the builder finds another way or asks — it does not look.

## Why this is stated explicitly

Entorhinal is a system that remembers. The party that builds the memory must
not treat the contents of that memory as its own working material. Authority
to build is not authority to know.
