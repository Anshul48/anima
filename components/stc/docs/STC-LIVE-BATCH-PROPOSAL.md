# Live-model batch proposal (decision ask, no spend authorized yet)

Quota-free work has established everything it can: genuine DSH boots with
the STC bundle (host + client faces verified), 7 tools + policy gate work
through the real agent loop (6/6 e2e), mechanics battery selects b2-gated
(3/3, theoracle-scored). What remains unknowable without live models is
**task quality**: whether a model driving these tools actually completes
real software tasks, and which delivery policy does it best.

## Question to decide

On real tasks, does b2-gated (preview→confirm→run→verify) beat b1-direct
(run→verify) and b0-single-agent (free tool use), measured by verified
task success first, then regressions, interventions, time, and tokens?
Inconclusive keeps b2-gated (mechanics winner) as the blessed delivery
policy; nothing auto-promotes.

## Design (predeclared)

- **Policies**: b0-single-agent (DSH headless + stc tools, free choice),
  b1-direct, b2-gated. Compositions = versioned bundle+patch rows in
  `policy/candidates/`; registry-blessed only after this eval.
- **Tasks** (one per kind, dev set; held-out twins reserved for
  qualification and never shown to policy authors):
  1. new feature in a scratch repo (add a CLI flag),
  2. unfamiliar-repo change (this STC repo: docs-only edit),
  3. bug repair (seeded failing test in scratch repo),
  4. cross-module change (probe flag plumbed tool→render),
  5. ambiguous spec (resolvable via one ask-user round),
  6. visible-UI task (prototype button; judged by DOM assertion, not pixels).
- **Harness**: headless DSH per episode with per-policy patch overlays;
  Python-SDK runner batching (or scripted CLI turns); theoracle scores
  from session events + run records. Failures/timeouts in denominator.
- **Stop rules**: abort a policy after 3 consecutive fault-handling
  failures; abort the batch if spend hits 80% of cap with no separation;
  predeclared bounds per episode (15 min, model-call ceiling).
- **Spend control**: hard cap (operator sets the number), per-episode
  ceilings, dry-run cost estimate first, spend ledger per episode.

## Cost estimate (to refine at approval time)

6 tasks × 3 policies = 18 episodes. Pilot evidence: dry-run backend legs
take ~6 s with zero model calls; model legs dominate. Assuming ≤15 min
and a mid-size model per episode, the batch is an overnight run; cost is
bounded by (episodes × per-episode token ceiling) + 20% buffer. Exact
figures depend on the operator's model choice and cap.

## Expected information gain

- Verified-success ranking of b0/b1/b2 on real tasks (the selection the
  mandate requires).
- Intervention/recovery/regression profiles per policy (inputs to the
  blessed policy's guardrails).
- A reusable eval battery + held-out set for the discovery lane.

## Alternatives

- **Defer live batch, ship b2-gated on mechanics**: viable; workspace is
  fully functional, but the delivery-policy claim stays mechanics-only.
  Recommended if budget is zero: label honestly, run the batch later.
- **Reduce to 2 policies × 3 tasks**: cheaper pilot; weaker selection
  power, still exercises the harness end to end.
- **Human-driven episodes**: operator drives the 6 tasks in `dsh web`
  manually; zero model spend, but measures UX, not policy quality.

## Ask

1. Approve a live batch (full / pilot / deferred) and set the hard cap.
2. Name the model + key source (DeepSeek API key env, account, or other).
3. Confirm held-out custody (operator holds twins; I never see them).

Until then: no live calls; discovery lane accepts only quota-free
candidates; b2-gated stays blessed-on-mechanics, labeled as such.
