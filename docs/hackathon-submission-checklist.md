# Nebius × NVIDIA Global AI Hackathon — Submission Checklist

Checked against the [official Devpost overview](https://nebiusglobalaihackathon.devpost.com/) and [official rules](https://nebiusglobalaihackathon.devpost.com/rules) on 2026-10-30. The form may impose additional field limits or instructions; follow the live form if it differs.

## Required submission items

- [ ] Complete and submit the Devpost entry before **2026-10-30 10:00 PDT** (17:00 UTC / 22:30 India Standard Time). Saving a draft is not the same as submitting the entry.
- [ ] Select one of the listed tracks. **Best Apps and Agents** is the lower-overclaim fit for the current plan-and-handoff copilot. **Coding and Agentic Engineering** is also relevant as a developer tool, but the current product does not let Nemotron write, run, or test arbitrary code; disclose that limitation if selecting it.
- [ ] Enter the project description and explain the features, intended user, and how the workflow operates.
- [ ] Provide a URL to a working demo, hosted application, or test build. This is distinct from the source repository URL. A [mock-only Windows source package](https://raw.githubusercontent.com/kitranet/devrelay-ai/acdf44d7a332e8762f29761dcd86ca775bf3c849/test-build-dist/DevRelay-AI-TestBuild.zip) with launcher scripts is available; it requires Python/Node and dependency downloads. It is not hosted and is not a precompiled installer. Confirm with organizers that this package qualifies before entering its URL. See [Windows test-build instructions](windows-test-build.md).
- [ ] Provide a URL to the public source repository. Verify that it is publicly accessible, contains the required files, and displays the Apache-2.0 license in the repository’s About/license area.
- [ ] Upload the final video to YouTube and make it **Public**. Add that public watch URL to Devpost. The local file is `demo-recordings/submission-recording.mp4`; it is 1920×1080 and 162.545 seconds (2:42.5). Listen through it once for voice clarity, synchronization, and accurate live-versus-mock language. Do not include copyrighted music or third-party marks without permission.
- [ ] Provide feedback on Nebius Token Factory and the NVIDIA models/tools used. Keep it factual and based on your own experience.
- [ ] If the project existed before the submission period, explain the substantial work completed during **2026-08-26 through 2026-10-30**.
- [ ] Confirm the entrant/team representative is authorized and that eligibility and rights statements are accurate.

The rules require a working project that makes a runtime call to Nebius Token Factory or runs on Nebius AI Cloud and uses at least one NVIDIA open-source model. They also require the project to remain available free of charge and without restriction for judging and testing through the end of the judging period, **2026-12-23 12:00 PST**. If the site is private, the rules say to include login credentials in the testing instructions. Do not expose a service without the reviewed authentication and access controls; resolve judge access before submitting.

## Verified project facts for the form

- DevRelay statically analyzes only configured repository IDs and uses synthetic repositories for the demonstration.
- NVIDIA Nemotron 3.5 Lightning (`nvidia/Nemotron-3_5-Lightning`) was called through Nebius Token Factory for a synthetic continuity-pipeline investigation plan.
- A completed local telemetry record reports provider HTTP 200, a completed response, schema validation passed, citation validation passed, 5 verified source references, 0 unsupported references, 4,652 input tokens, 906 output tokens, 0 reasoning tokens, and 6,277 ms latency.
- The recorded estimated cost is **$0.00049656** based on the usage and published token-rate configuration. Actual provider billing is unavailable; do not call this an invoice or exact amount billed.
- The run-history screen separates completed plans, failed/truncated attempts, and mock runs. Not every inference attempt succeeded.
- Mock remains the default and is not a Nemotron result. Live inference is explicitly opted into, request-limited, and has no automatic retries or provider fallback.
- The plan and citations are validated against analyzed evidence. Human review remains required. A plan-only handoff is not an applied fix.
- The separate deterministic proposal preview is allowlisted to a synthetic calculator division-by-zero scenario; it is not Nemotron-generated and is not a Northstar pipeline patch.
- No repository code is automatically changed or executed. Runtime validation is `not_run` because no trusted isolated executor is configured.

## Project description draft

**DevRelay AI helps the next engineer continue an investigation with repository context, source evidence, and an explicit record of what remains unknown.** It statically maps an authorized synthetic codebase, sends bounded evidence to NVIDIA Nemotron through Nebius Token Factory for a structured investigation plan, validates the response and its citations locally, and carries the plan into a reviewable handoff. Per-run history records sanitized provider status, token use, latency, validation results, and an estimated cost when usage is available.

The system is deliberately plan-first. It does not apply model-generated code or execute repository code. Human review is required, and runtime validation remains unavailable without a trusted isolated executor. Mock inference is the default for offline testing and is labeled separately from genuine Nemotron requests.

Before pasting, adapt this text to the actual Devpost field limits and make sure its statements match the final video and the exact public build you provide.

## What changed during the submission period — draft

Use this only if the dates accurately describe the project’s development history:

> During the hackathon submission period, DevRelay AI grew from a local repository-analysis prototype into an evidence-backed engineering handoff workflow. We added bounded source excerpts, structured Nemotron planning through Nebius Token Factory, schema and citation validation, plan integrity checks, plan-only review and handoff, sanitized per-run usage and estimated-cost history, and repeatable offline evaluation. We also added a synthetic multi-module pipeline incident to demonstrate cross-file investigation. The workflow remains read-only: no model-generated patch is applied, no repository code is executed, and runtime validation is reported as not run.

## Feedback notes to complete in your own words

The form asks for feedback on Nebius Token Factory and the NVIDIA technologies used. Do not submit a fabricated endorsement. Note your actual experience with model availability, request setup, structured output, latency, usage reporting, and any failed/truncated attempts. Separate provider behavior from DevRelay’s own validation and UI behavior.

## Pre-submit access check

- [ ] The public test-build archive downloads without authentication, and its instructions are verified on a clean Windows machine; it exposes only the synthetic fixture and uses mock inference. Verify its SHA-256 using the [published checksum](https://raw.githubusercontent.com/kitranet/devrelay-ai/acdf44d7a332e8762f29761dcd86ca775bf3c849/test-build-dist/SHA256SUMS.txt).
- [ ] The URL remains available and free to judges through 2026-12-23.
- [ ] Login instructions work without sharing personal or production credentials; live paid inference is not available to judges unless separately budgeted and controlled.
- [ ] The public GitHub repository contains the exact reviewed source, setup instructions, license, and no secrets or local state.
- [ ] The YouTube video is public, under three minutes, plays at 1080p, and has clear narration and truthful provider disclosures.
- [ ] The project description, track, README, demo URL, video, and recorded behavior all agree.
- [ ] Click **Submit** in Devpost and verify that the entry shows as submitted, not draft.

## Important unresolved blocker

There is no hosted judge-access URL. The API itself has no authentication; the Next.js dashboard gate does not make it safe to expose FastAPI directly. The downloadable package is a local test build, not a hosted demo, and its acceptance as a test build is unconfirmed. Ask the organizers/Devpost whether this package satisfies the requirement. Do not expose loopback services or describe the package as an always-on application.
