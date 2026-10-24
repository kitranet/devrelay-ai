# Phase 8D.4/8D.5 video storyboard: continuity across an incident

Target: 2:50 (170 seconds). The automated continuity recorder is live-only and
requires a separate explicit authorization for one Nebius request. It must not
substitute mock output if the live response fails. The calculator recorder is a
separate mock fallback and must remain visibly labeled as mock.

| Time | Screen | Accurate narration point |
|---|---|---|
| 0:00–0:25 | Dashboard and selected `continuity-pipeline-fixture`. | Engineering context gets lost during handoffs; this synthetic incident starts with symptoms and open questions, not a supplied diagnosis. |
| 0:25–0:50 | Static analysis, modules, imports, tests, and dependency manifest. | The configured-ID scanner reads repository structure without running its code. |
| 0:50–1:25 | Submit the incident request; show actual provider/model and plan state. | In the live path, Nemotron generates the structured investigation plan. In the fallback, the visible output is deterministic mock and is not AI-generated. |
| 1:25–1:50 | Relevant files, exact citations, supplied source excerpts, findings, and questions. | Excerpts are bounded, hash-bound source evidence. Observed facts are tied to excerpt references; hypotheses remain suspected. |
| 1:50–2:15 | Plan review panel and unverified local reviewer-label explanation. | A reviewer must record a justified decision before a handoff can be marked reviewed. This panel reviews the plan, not code. |
| 2:15–2:40 | Create the plan-only engineering handoff; show `awaiting human review`. | The report carries the stored plan, evidence, findings, questions, and proposed next steps; it contains no code diff. |
| 2:40–2:50 | End on human approval required, execution `not_started`, runtime `not_run`. | No patch is proposed, applied, or executed. Review labels are unverified and storage is process-local. |

The existing `frontend/scripts/record-demo.mjs` is the calculator/mock
fallback. The separate `frontend/scripts/record-continuity-live-demo.mjs`
requires `DEVRELAY_LIVE_DEMO_AUTHORIZED=YES`, an available durable one-request
quota, and an actual Nebius credential in the backend process. Do not run it
without authorization for that single request. It verifies the provider and
model shown by the returned plan and stops on failure without retry/fallback.
The app has no incident-brief screen, so use voiceover for the scenario rather
than implying an in-app incident page exists.
