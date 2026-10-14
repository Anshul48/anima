# SST native Windows qualification receipt

Inspected and exercised from the native Windows architect session on 2026-10-04. This is an attributable update to the earlier Linux delivery record. STC/TRACE source, pins and active runs were not changed. No commit was created.

The delivered cand-02 implementation matches the landed implementation across 83 source/test/configuration files. Frozen dependencies installed in `.delivery/windows-qualification/.venv` with Python 3.12.0 on Windows. The sandboxed download initially failed through its network proxy; the approved host download succeeded. Both setup logs are retained.

| Check against original cand-02 | Observed result | Evidence |
|---|---|---|
| Ruff check | exit 0 | `.delivery/windows-qualification/ruff-check.log` and `.exit` |
| Ruff format check | exit 0, 88 files formatted | `.delivery/windows-qualification/ruff-format.log` and `.exit` |
| Strict mypy | exit 0, 76 source files | `.delivery/windows-qualification/mypy.log` and `.exit` |
| Pytest | exit 0, 145 passed in 64.41 seconds | `.delivery/windows-qualification/pytest.log` and `.exit` |
| Native CLI positive/negative wiring | exits 0/2, TEST provider identified, champion present/absent respectively | `browser-20261004-135339/cli-*.json` under the evidence directory |

Passing these checks did not establish browser functionality. The original browser run failed with `SyntaxError: Unexpected token ')'` on the run page. Progress/budgets stayed at "Loading" and the alternatives/actions script did not execute. `src/sst/ui/pages.py` lines 599 and 600 each have an extra closing parenthesis in the graph element mapping. The browser parses that code even when the Graph tab is not selected. The HTTP journey test fetches the HTML but does not execute its JavaScript.

Original browser failure: `.delivery/windows-qualification/browser-20261004-135339/report.json` and `failure.png`. An earlier sandbox browser attempt failed on Chrome IPC access; its separate report/logs are preserved at `browser-20261004-135048`. The subsequent browser checks used approved host execution, hidden headless Chrome and a fresh verification profile.

The two-line correction is prepared in `.delivery/windows-qualification/ui-browser-fix.patch`. It passes `git apply --check --whitespace=error` against the actual dirty source tree. It has been applied only to `.delivery/windows-qualification/cand-02-browser-fix`; the landed source and original cand-02 snapshot retain the original fault for their owner to integrate deliberately.

- Original `pages.py` SHA256: `522bde957c3cbfb39dd2c963cb9867d0ab7989268f4f7d535bda9fc056a9aca9`.
- Corrected `pages.py` SHA256: `7b4be7c4813775e9ba2fac2aa0171d81a8d293b437d599ff5a5600dfab365add`.
- Patch SHA256: `f95b59bbfb4de189cce094277d909c9c210aeb9db0c216c8ffac2f24e0817dd9`.

On the isolated corrected candidate, actual Chrome interactions passed: task creation, run submission, rendered progress/result and three alternatives, visible TEST identity, decision submission, promotion with verified test-workspace file effects, reopening persisted results, honest negative result without promotion, and cancellation of a running verifier without promotion. No uncaught JavaScript errors were recorded. The corrected page also passes Ruff lint/format checks and the existing HTTP journey test (1 passed). Evidence: `.delivery/windows-qualification/browser-20261004-135819/report.json`, screenshots and `pytest-browser-fix.log`. The script at `native_browser_probe.py` retains the reproduction/verification procedure.

The server logged `ConnectionAbortedError` when browser navigation interrupted an in-flight request. The journey completed; the disconnect logging remains an observed robustness/polish issue, not a hidden clean-log claim. The fixture gateway supplies known code, so these results establish browser/backend execution mechanics, not real generation capability or search superiority. Responsive/mobile usability and the optional CDN graph were not qualified by this desktop flow.

The delivered Windows launcher had a separate defect: `uv run sst ui --project ...` uses an unsupported option and its wrapper returned exit 0 despite the CLI error. `.delivery/run-ui.ps1` now resolves the requested project before changing directories, uses `--project-path`, checks synchronization failure and propagates the CLI exit code. The corrected launcher was exercised successfully to a live `/healthz` response. Its verification process tree was then deliberately stopped; the recorded exit 1 is cleanup after the observed healthy launch.

Remaining completion work:

1. SST owner: integrate the prepared two-line browser correction into source and the delivered snapshot, refresh the manifest/patch, and keep the browser regression check with the assembled candidate. This is routine authorized work, not a new request for human approval.
2. Configure an intended real provider and observe useful model-generated search through the actual caller/UI with domain checks, attributable alternatives, budget accounting and honest failures. No API keys were configured in this Windows session. The current CLI selects a real gateway only when `OPENAI_API_KEY` is set; a `DEEPSEEK_API_KEY` alone is not sufficient for that selection. The UI's `operator` label delegates to that default gateway; it does not implement an independent manual candidate-submission channel.
3. STC owner: resolve the Rule-4 explicit `CRITIQUE_FAILED` veto, the documented test recalibrations, a deliberate source pin and actual caller qualification. Current inspected STC code still implements Rules 1-3. SST's disposal exercise and handoff do not substitute for owner adoption or a real caller run.
4. Release bookkeeping: select the final assembled version and commit/publish under the applicable authorization. A commit is needed for a Git pin; it is not required to execute the runnable delivery. No commit authorization was inferred from the status question.

Standalone SST completion and STC integration completion retain separate status. Windows tooling availability and the old Linux interop failure no longer justify asking the user to run the native gate suite. The landed browser fault remains concrete SST work; live generation and consumer adoption remain separate qualification dependencies.
