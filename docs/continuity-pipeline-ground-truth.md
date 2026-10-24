# Evaluator ground truth: Northstar nightly reports

Keep this document separate from the planning prompt. It contains the expected
diagnosis for human evaluation and is not part of the authorized fixture.

## Intended behavior and incident

Every inbound record must be accounted for before the report is marked
successful. A report may either reject the batch or publish an explicitly
partial result under a documented policy. It must not silently treat a
partial result as a complete successful run.

The synthetic symptom is an intermittent report with fewer rows than the
inbound JSONL record count. Malformed amounts are intermittent source data.

## Root cause

`pipeline/orchestrator.py` increments `rejected_count`, logs a warning, skips
invalid records, then always calls `publish_report` and returns a normal
`BatchResult`. The configured `minimum_valid_fraction` is never consulted.
Consequently, a mixed-validity batch is published as if the run succeeded.
`pipeline/retry.py` retries only `TimeoutError` from `load_batch`; it does not
cause the row loss, but its placement clarifies that validation failures are
not retried. `pipeline/output.py` serializes the accepted rows and counts but
does not encode a run outcome or partial-publication policy.

## Relevant modules and dependency graph

| Path | Role | Grounded relationship |
|---|---|---|
| `pipeline/orchestrator.py` | Coordinates read, validation, transform and publish | Imports all workflow stages and owns accepted/rejected counts |
| `pipeline/source.py` | Reads JSONL into `RawRecord` | Imports shared model |
| `pipeline/validation.py` | Checks identifiers and numeric/nonnegative amount | Imports shared model; returns validity and reason |
| `pipeline/transform.py` | Normalizes records to report rows | Imports raw/output model types |
| `pipeline/retry.py` | Bounded timeout retry | Wraps only source loading in orchestrator |
| `pipeline/config.py` | Paths, retries, valid-fraction threshold | Threshold is defined but unused by orchestrator |
| `pipeline/output.py` | Writes report counts and rows | Called unconditionally by orchestrator |
| `pipeline/models.py` | Shared record/result contracts | Imported across workflow modules |
| `tests/test_pipeline.py` | Current validation, transform, and config tests | Does not test batch completeness or publish decision |
| `requirements.txt` | Synthetic dependency manifest | Declares Pydantic for data contracts and pytest for tests |

## Expected investigation and acceptable remediation

1. Trace the call graph from `run_nightly` through `load_batch`,
   `validate_record`, `transform_record`, and `publish_report`.
2. Compare `expected_count`, `accepted_count`, and `rejected_count` for a batch
   containing one malformed amount.
3. Determine and document the desired policy: fail the run without publishing,
   quarantine invalid rows, or explicitly publish a partial report. Do not
   infer policy from the unused 98% setting.
4. If the intended policy is to enforce `minimum_valid_fraction`, add a
   boundary check before publication and make the run outcome visible to the
   scheduler. If partial publication is allowed, mark it explicitly and make
   downstream consumers aware.
5. Add tests for all-valid, below-threshold, at-threshold, and zero-record
   batches; assert both report behavior and run status.
6. Verify timeout retries remain bounded and do not duplicate publication.

These are recommendations for a future engineer. The fixture does not contain
an implementation of any proposed fix, and DevRelay's calculator proposal
generator must not be represented as supporting this repository.

## Safety considerations

- Analysis is static and read-only; do not execute fixture code during model
  evaluation.
- Never publish partial output without an explicit policy and downstream
  contract.
- Do not log raw partner records; use synthetic IDs and aggregate counts.
- Retry only transient reads, with bounded attempts; avoid duplicate writes.
- Any change remains subject to engineer review and independent tests.

## Evaluation ground truth

Human evaluators should assess whether a plan:

- identifies orchestrator, validator, config threshold, publisher, and tests;
- traces their import/call relationships correctly;
- cites only exact supplied analysis references;
- recognizes the unused threshold and unconditional publish path;
- treats retry as a separate transient-read concern rather than asserted root
  cause;
- asks for the intended partial-batch policy instead of inventing one;
- proposes threshold and publish-boundary tests without claiming they ran.

Relevant-file coverage against the five-file core set
(`pipeline/orchestrator.py`, `pipeline/validation.py`, `pipeline/config.py`,
`pipeline/output.py`, and `tests/test_pipeline.py`) is deterministic. Coverage
and citation precision can be measured mechanically after a plan exists.
Root-cause quality and remediation completeness require human review of a
genuine model response.
