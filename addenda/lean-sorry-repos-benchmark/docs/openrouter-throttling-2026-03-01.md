# OpenRouter Throttling Run Notes (2026-03-01)

Records a reproducible OpenRouter suite run focused on:
- handling temporary model throttling,
- checking practical model availability, and
- collecting a small hosted-model baseline snapshot.

## Suite Config and Command

Pinned config:
- `configs/openrouter-throttled-v3.json`

Run command:

```bash
cd addenda/lean-sorry-repos-benchmark
uv run python -m lean_sorry_repos_benchmark.suite_runner \
  --config configs/openrouter-throttled-v3.json \
  --out-dir ../../tmp/lean-suite-openrouter-throttled-v3
```

Output bundle:
- `../../tmp/lean-suite-openrouter-throttled-v3/suite_results.json`
- `../../tmp/lean-suite-openrouter-throttled-v3/suite_summary.md`

## Result Snapshot

Aggregate:
- `run_count=5`
- `success_count=5`
- `infra_failure_count=0`
- `model_error_run_count=2`

Per-model:
- `moonshotai/kimi-k2`: `valid_rate=1.0000`, `verification_success_rate_attempted=0.1250`, `generation_error_count=0`
- `qwen/qwen3-coder`: `valid_rate=1.0000`, `verification_success_rate_attempted=0.0938`, `generation_error_count=0`
- `google/gemma-3-27b-it:free`: `valid_rate=0.0938`, `verification_success_rate_attempted=0.0000`, `generation_error_count=29 (http_error)`
- `google/gemma-3-12b-it:free`: `valid_rate=0.0000`, `verification_success_rate_attempted=0.0000`, `generation_error_count=32 (http_error)`
- `arcee-ai/trinity-large-preview:free`: `valid_rate=0.8125`, `verification_success_rate_attempted=0.1250`, `generation_error_count=0`

Interpretation:
- Throttling and endpoint instability were model-specific (free Gemma variants) rather than suite-wide infrastructure failures.
- Retry settings (`count=2`, `domains=all`, kinds `http_error,timeout`) were not enough to salvage those specific free-model runs.

## Availability and Routing Notes

Observed during direct preflight probes:
- Some published `:free` model IDs intermittently returned `404` ("No endpoints found ...").
- Others returned `429` with explicit upstream rate-limit messages.

Practical workflow:
1. preflight candidate model IDs with a one-token chat call;
2. keep only routable models in the suite config;
3. keep retry enabled for transient `http_error` and timeout classes;
4. avoid baseline claims when `model_error_run_count > 0`.

