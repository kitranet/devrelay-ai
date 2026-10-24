# Synthetic incident brief: Northstar nightly reports

## Incident for the receiving engineer

Northstar is a fictional reporting service. Its 02:00 ingestion job has
intermittently published reports with fewer rows than the inbound batch. The
job dashboard still marks those runs successful. Downstream analysts noticed
the mismatch the following morning. The issue is easiest to reproduce when an
inbound batch contains a malformed amount.

## Departing-engineer handoff

The job reads newline-delimited records, validates and normalizes them, then
publishes a JSON report. A bounded retry helper is used for transient read
timeouts. The current operator has not established whether the retry behavior,
validation policy, or publish boundary explains the missing rows. Compare the
expected, accepted, and rejected counts and determine what conditions should
allow a report to be published. Do not change files during investigation.

## Request to enter in DevRelay

> Investigate why the 02:00 ingestion job can publish a successful report with
> fewer rows than the inbound batch. Trace orchestration, validation,
> transformation, retry, configuration, and publication behavior across the repository. Propose safe
> investigation steps, evidence to collect, and regression checks. Do not
> assume the root cause, change repository files, or execute code.

This brief intentionally describes symptoms and relevant areas without stating
the ground-truth defect. The separate ground-truth document is for evaluators
and must not be included in model prompt context.
