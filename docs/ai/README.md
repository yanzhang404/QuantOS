# AI Research Assistant

AI workflows are tool-driven. Agents may query datasets, modify reviewed code,
run backtests, compare experiments, and inspect artifacts. They may not invent
results, bypass risk review, expose secrets, or activate live trading.

## Daily intelligence Agent boundary

The daily intelligence workflow accepts a versioned JSON input rather than
giving a model direct write access to the homepage. An Agent or OpenClaw job may:

- fetch from an approved HTTPS/RSS source list;
- deduplicate stories by canonical URL and content identity;
- classify asset relevance, direction, confidence, and importance;
- provide a short factual summary with the original source URL.

It may not calculate the final sentiment score, change factor weights, run
commands, read arbitrary local files, access exchange credentials, or invoke
paper/live execution. QuantOS validates the Agent output, calculates the index
with a versioned deterministic formula, and persists the exact input SHA-256.

Recommended daily operation:

1. a scheduler invokes the single-writer `quantos intelligence refresh` job;
2. the job collects, validates, and publishes through the separate boundaries;
3. the Go API exposes the latest valid file read-only;
4. the homepage displays its timestamp, completeness, factors, and citations.

The refresh health record exposes last attempt, last success, fixed failure
code, and consecutive failures. It contains no response bodies, stack traces,
credentials, or autonomous trading controls.

External text is untrusted data. Summaries must never be interpreted as tool
instructions, and source content is not copied into prompts beyond the bounded
fields required for classification.
