# Phase 8D: final hackathon demo video

## Recording objective

Show how DevRelay preserves engineering context through a bounded handoff workflow: authorized repository → static analysis → task plan → verified evidence → fixed proposal → human decision → handoff report. Finish by **2:55**; keep the final public YouTube video under three minutes.

The recommended recording is a repeatable local walkthrough using the synthetic `planning-fixture` and deterministic mock inference. Keep the dashboard's visible `MOCK MODE` banner in frame when the plan is generated. This recording does not make a Nemotron request. The application can make an explicitly opted-in Nebius planning request, but the current video should not imply the mock plan is a model response.

## Timed storyboard and voiceover

| Time | Screen direction | Voiceover |
|---|---|---|
| **0:00–0:25** Knowledge-transfer problem | Open on the authenticated DevRelay workspace. Keep the heading, repository selector, backend status, and “Local analysis · Read-only” label visible. | “When an engineer hands off an unfamiliar codebase, the next person often receives a task without the context behind it: which files matter, what evidence supports the diagnosis, and what still needs review. DevRelay is designed to make that context traceable before work moves forward.” |
| **0:25–0:50** Authorized repository analysis | Select `planning-fixture`; click **Analyze repository**. Show discovered modules and file/test counts. Open the imports/dependency and source-reference details briefly. | “The operator authorizes a repository by ID. Here, that ID maps to a small synthetic Python calculator. DevRelay uses bounded static analysis to map Python modules, symbols, imports, dependency manifests, and tests. It parses source structure; it does not import or run repository code.” |
| **0:50–1:20** Task plan | Enter “Fix the division by zero defect in the calculator” and generate the plan. Keep the provider badge and mock disclosure visible. Show plan status, relevant files, proposed steps, risks, and validation requirements. | “For this repeatable recording, planning uses the deterministic mock provider, clearly labeled on screen. The product also supports an explicitly selected Nebius Token Factory provider for NVIDIA Nemotron planning. The plan shown here is a mock scenario result, not Nemotron output. In either path, the returned plan must satisfy the structured schema before the application presents it.” |
| **1:20–1:45** Verified evidence | Scroll to supporting evidence and step citations. Show the relevant `package/calculator.py` and calculator test references; if present, point out that unverified citations are shown separately. | “A plan is useful only if its claims can be checked. DevRelay verifies each citation against the authorized static-analysis snapshot. Verified references are shown as supporting evidence; rejected references are explicitly unverified. This makes it possible for the receiving engineer to inspect the cited source instead of trusting a plausible-looking path.” |
| **1:45–2:10** Guarded deterministic proposal | Click **Generate code proposal**. Show `Proposal generator: deterministic allowlist`, the target file, static findings, and unified diff. Keep “Runtime validation: not run” in view. | “For this one synthetic calculator task, the server checks plan provenance and the current repository snapshot, then creates a fixed, allowlisted diff in memory. Nemotron does not author the patch. The proposal is a review preview: source files remain unchanged, and no repository tests or code are executed.” |
| **2:10–2:35** Human review and handoff | In the local development-only review setup, enter reviewer label `demo_reviewer`, a brief justification, and optionally one question. Record **Approve for consideration**. Show the decision history, then click **Generate report** and briefly show the report or Markdown download controls. | “A human must review the proposal. This local demonstration records a decision with a justification and binds it to the proposal and source hashes. The reviewer label is unverified, and approval means further consideration only—it does not apply the diff. The handoff report carries forward the plan, evidence, proposal, decision, questions, and the honest runtime status.” |
| **2:35–2:55** Safety and outcome | End on the handoff’s provenance, review decision, and `not_run` status. Use a separate full-screen text card for historical live metrics if including them; do not overlay them on the mock plan. | “The outcome is a reviewable engineering handoff, not an autonomous coding agent. Analysis is static, the proposal is deterministic, human approval is required, and execution remains unavailable. A separate earlier live test used Nebius Token Factory with NVIDIA Nemotron 3.5 Lightning; those historical measurements are disclosed separately from this mock walkthrough.” |

### Optional historical live-evidence card

If the video includes the existing Phase 6B.2 observation, use a plain title card while the dashboard is not showing a mock plan:

> **Separate historical live test — Phase 6B.2**
> Nebius Token Factory · `nvidia/Nemotron-3_5-Lightning`
> 1,349 input · 381 output · 0 reasoning tokens · 2,823 ms
> 5 verified citations · 0 unsupported citations
> Estimated cost: $0.00017238 (estimate, not a billing statement)

This is the user-provided historical result recorded in [Phase 7 evaluation](phase-7-evaluation.md) and the machine-readable report. It is not a measurement from the mock workflow or a live call made for this video. Do not recreate a model response, fabricate a screenshot, or edit mock output to resemble live inference.

## Judge notes and accurate claims

- **Implemented and shown:** authorized repository ID; static Python repository analysis; dependency-manifest discovery; structured planning; local source-reference verification; deterministic proposal for one fixed synthetic calculator transformation; human-review gate; Markdown handoff; read-only source behavior.
- **Provider disclosure:** the recommended current recording uses `provider=mock`, `is_mock=true`, model `devrelay-mock-v1`. The historical live observation is separate evidence of one successful Nemotron planning request. The video must not imply that the currently displayed mock plan came from NVIDIA.
- **Proposal disclosure:** the calculator diff comes from a deterministic allowlist, never from model-authored patch text. The source file is unchanged and runtime validation is `not_run`.
- **Review disclosure:** local review is enabled only in development and loopback for this recording; the reviewer name is an unverified label and decisions/history are process-local prototype data.
- **Not demonstrated:** broad-language repository support, team collaboration, durable audit storage, sandboxed test execution, autonomous code application, public deployment, or a full browser-driven live Nemotron-to-review E2E run.
- **Proposal wording:** the proposal card identifies this artifact as a “Deterministic proposal preview” and labels its generator as a deterministic allowlist. The separate plan-provider label identifies whether planning used mock or Nebius; Nemotron does not author the diff.

## Optional live capture

A fresh live request is not needed to tell the story because a historical successful result is already documented. If the team decides a new live capture is materially better, treat it as a separate paid operation: first check current account billing/model access, establish a small durable request quota and provider-side controls, confirm only the synthetic fixture is authorized, verify the server says Nebius and the intended model, and obtain explicit authorization for exactly one request. Do not retry, switch providers, or use the live result as if it were the mock evaluation. The $25 promotional credit is not a spending cap.
