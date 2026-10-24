"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { analyzeRepository, checkBackend, createProposal, generateHandoff, getInferenceStatus, getLocalReviewStatus, getReviewHistory, getSandboxReadiness, planTask, requestRuntimeValidation, submitReview } from "@/lib/api";
import { handoffToMarkdown } from "@/lib/handoff-markdown";
import type { CodeChangeProposal, HandoffReport, InferenceStatus, LocalReviewStatus, RepositoryAnalysis, ReviewDecision, ReviewHistory, RuntimeValidationEvidence, SandboxReadiness, TaskPlan } from "@/lib/types";

type BackendState = "checking" | "connected" | "offline";
const reviewerIdentifierPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const credentialLikeReviewerIdentifier = /(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*\S+|nvapi-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})/i;

function reviewerIdentifierError(value: string): string | null {
  const normalized = value.trim();
  if (!normalized) return "Enter a reviewer label.";
  if (!reviewerIdentifierPattern.test(normalized)) {
    return "Use 1–64 characters: start with a letter or number, then use only letters, numbers, periods, underscores, or hyphens. Spaces are not allowed.";
  }
  if (credentialLikeReviewerIdentifier.test(normalized)) {
    return "Reviewer labels cannot contain credential-like values.";
  }
  return null;
}

const configuredRepositories = (process.env.NEXT_PUBLIC_REPOSITORY_IDS ?? "")
  .split(",")
  .map((repositoryId) => repositoryId.trim())
  .filter((repositoryId) => /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(repositoryId));

function BrandMark() {
  return <span aria-hidden="true" className="brand-mark">D<span>.</span></span>;
}

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "good" | "warning" | "muted" }) {
  return <span className={`badge badge-${tone}`}><span className="badge-dot" />{children}</span>;
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="empty-state"><span className="empty-icon" aria-hidden="true">↗</span><div><strong>{title}</strong><p>{detail}</p></div></div>;
}

function Reference({ path, line }: { path: string; line: number }) {
  return <code className="source-ref">{path}<span>:{line}</span></code>;
}

export default function Dashboard() {
  const [repositoryId, setRepositoryId] = useState(configuredRepositories[0] ?? "");
  const [backend, setBackend] = useState<BackendState>("checking");
  const [backendMessage, setBackendMessage] = useState("Checking local API…");
  const [analysis, setAnalysis] = useState<RepositoryAnalysis | null>(null);
  const [plan, setPlan] = useState<TaskPlan | null>(null);
  const [proposal, setProposal] = useState<CodeChangeProposal | null>(null);
  const [reviewStatus, setReviewStatus] = useState<LocalReviewStatus | null>(null);
  const [inferenceStatus, setInferenceStatus] = useState<InferenceStatus | null>(null);
  const [reviewHistory, setReviewHistory] = useState<ReviewHistory | null>(null);
  const [sandboxReadiness, setSandboxReadiness] = useState<SandboxReadiness | null>(null);
  const [runtimeEvidence, setRuntimeEvidence] = useState<RuntimeValidationEvidence | null>(null);
  const [handoff, setHandoff] = useState<HandoffReport | null>(null);
  const [reviewerIdentifier, setReviewerIdentifier] = useState(process.env.NEXT_PUBLIC_LOCAL_REVIEWER_ID ?? "local-reviewer");
  const [reviewJustification, setReviewJustification] = useState("");
  const [outstandingQuestions, setOutstandingQuestions] = useState("");
  const [executionAuthorizer, setExecutionAuthorizer] = useState(process.env.NEXT_PUBLIC_EXECUTION_AUTHORIZER_ID ?? "local_authorizer");
  const [executionPurpose, setExecutionPurpose] = useState("");
  const [taskDescription, setTaskDescription] = useState("");
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [planningBusy, setPlanningBusy] = useState(false);
  const [proposalBusy, setProposalBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [runtimeBusy, setRuntimeBusy] = useState(false);
  const [handoffBusy, setHandoffBusy] = useState(false);
  const [markdownStatus, setMarkdownStatus] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    checkBackend().then((result) => {
      if (!active) return;
      setBackend(result.status === "ok" ? "connected" : "offline");
      setBackendMessage(result.status === "ok" ? "FastAPI is responding" : "Unexpected health response");
    }).catch((reason: unknown) => {
      if (!active) return;
      setBackend("offline");
      setBackendMessage(reason instanceof Error ? reason.message : "Backend unavailable");
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    getLocalReviewStatus().then(setReviewStatus).catch(() => setReviewStatus(null));
  }, []);

  useEffect(() => {
    getInferenceStatus().then(setInferenceStatus).catch(() => setInferenceStatus(null));
  }, []);

  useEffect(() => {
    getSandboxReadiness().then(setSandboxReadiness).catch(() => setSandboxReadiness(null));
  }, []);

  useEffect(() => {
    if (!proposal || !reviewStatus?.enabled) return;
    let active = true;
    getReviewHistory(proposal.proposal_id).then((result) => {
      if (active) setReviewHistory(result);
    }).catch(() => {
      if (active) setReviewHistory(null);
    });
    return () => { active = false; };
  }, [proposal, reviewStatus?.enabled]);

  const providerLabel = useMemo(() => {
    if (!plan) return inferenceStatus?.provider === "mock" ? "Mock (offline, no external calls)" : inferenceStatus?.provider === "nebius" ? "Nebius Token Factory" : "Status unavailable";
    return plan.is_mock ? "Mock provider" : "Nebius Token Factory";
  }, [plan, inferenceStatus]);

  const inferenceStateLabel = useMemo(() => {
    if (!inferenceStatus) return "Live-inference status unavailable.";
    if (inferenceStatus.provider === "mock") return "Live inference disabled; deterministic mock, no external model calls.";
    if (!inferenceStatus.live_inference_enabled) return "Nebius is selected, but live inference is disabled by the operator.";
    if (!inferenceStatus.credentials_configured) return "Live inference is enabled, but the server credential is not configured.";
    if (inferenceStatus.quota_status === "available") return `Live request allowance: ${inferenceStatus.quota_remaining} remaining.`;
    if (inferenceStatus.quota_status === "exhausted") return "Live inference request allowance exhausted.";
    return "Live inference blocked because quota status is unavailable.";
  }, [inferenceStatus]);

  async function runAnalysis() {
    if (!repositoryId) return;
    setAnalysisBusy(true);
    setError(null);
    setAnalysis(null);
    try {
      const result = await analyzeRepository(repositoryId);
      setAnalysis(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Repository analysis failed.");
    } finally {
      setAnalysisBusy(false);
    }
  }

  async function submitPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!repositoryId) return;
    setPlanningBusy(true);
    setError(null);
    setPlan(null);
    setProposal(null);
    try {
      const nextPlan = await planTask(repositoryId, taskDescription.trim());
      setPlan(nextPlan);
      setProposal(null);
      setReviewHistory(null);
      setRuntimeEvidence(null);
      setHandoff(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Task planning failed.");
    } finally {
      setPlanningBusy(false);
    }
  }

  async function generateProposal() {
    if (!plan || !repositoryId) return;
    setProposalBusy(true);
    setError(null);
    try {
      const nextProposal = await createProposal(repositoryId, plan.task_id);
      setProposal(nextProposal);
      setReviewHistory(null);
      setRuntimeEvidence(null);
      setHandoff(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Proposal generation failed.");
    } finally {
      setProposalBusy(false);
    }
  }

  async function recordReview(decision: ReviewDecision) {
    if (!proposal || !reviewStatus?.enabled || !reviewJustification.trim()) return;
    const identifierError = reviewerIdentifierError(reviewerIdentifier);
    if (identifierError) {
      setError(identifierError);
      return;
    }
    setReviewBusy(true);
    setError(null);
    try {
      const review = await submitReview({
        proposal_id: proposal.proposal_id,
        decision,
        reviewer_identifier: reviewerIdentifier.trim(),
        justification: reviewJustification,
        proposal_version: proposal.version,
        source_sha256: proposal.target_files[0].original_sha256,
        diff_sha256: proposal.diff_sha256,
        outstanding_questions: outstandingQuestions.split("\n").map((value) => value.trim()).filter(Boolean).slice(0, 12),
      });
      setProposal({ ...proposal, lifecycle_state: review.proposal_lifecycle_state, version: proposal.version + 1 });
      setReviewJustification("");
      setOutstandingQuestions("");
      setHandoff(null);
    } catch (reason) {
      try {
        setReviewHistory(await getReviewHistory(proposal.proposal_id));
      } catch {
        // A failed audit-history refresh must not replace the original decision error.
      }
      const message = reason instanceof Error ? reason.message : "Review decision could not be recorded.";
      setError(message.startsWith("Review request validation failed")
        ? "The review was not recorded. Check the reviewer label format and required review fields; no decision was saved."
        : message);
    } finally {
      setReviewBusy(false);
    }
  }

  async function buildHandoff() {
    if (!proposal) return;
    setHandoffBusy(true);
    setError(null);
    try {
      const report = await generateHandoff(proposal.proposal_id);
      setHandoff(report);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Handoff report generation failed.");
    } finally {
      setHandoffBusy(false);
    }
  }

  async function requestRuntimeRun() {
    if (!proposal || !sandboxReadiness?.enabled || proposal.lifecycle_state !== "review_approved") return;
    setRuntimeBusy(true);
    setError(null);
    try {
      const evidence = await requestRuntimeValidation({
        proposal_id: proposal.proposal_id,
        proposal_version: proposal.version,
        source_sha256: proposal.target_files[0].original_sha256,
        diff_sha256: proposal.diff_sha256,
        test_case: "calculator_unit_tests",
        authorization: { authorizer_identifier: executionAuthorizer.trim(), purpose: executionPurpose.trim() },
      });
      setRuntimeEvidence(evidence);
      setExecutionPurpose("");
      setHandoff(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Runtime validation request failed.");
    } finally {
      setRuntimeBusy(false);
    }
  }

  async function copyHandoffMarkdown() {
    if (!handoff) return;
    try {
      await navigator.clipboard.writeText(handoffToMarkdown(handoff));
      setMarkdownStatus("Markdown copied.");
    } catch {
      setMarkdownStatus("Clipboard access is unavailable; use Download Markdown instead.");
    }
  }

  function downloadHandoffMarkdown() {
    if (!handoff) return;
    const file = new Blob([handoffToMarkdown(handoff)], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = `devrelay-handoff-${handoff.report_id}.md`;
    link.click();
    URL.revokeObjectURL(url);
    setMarkdownStatus("Markdown download prepared.");
  }

  function onRepositoryChange(value: string) {
    setRepositoryId(value);
    setAnalysis(null);
    setPlan(null);
    setProposal(null);
    setReviewHistory(null);
    setHandoff(null);
    setError(null);
  }

  const isMock = plan?.is_mock === true;

  return (
    <div className="app-shell">
      <header className="topbar">
        <a href="#overview" className="brand" aria-label="DevRelay AI home">
          <BrandMark />
          <span className="brand-name">devrelay<span>ai</span></span>
        </a>
        <nav className="top-nav" aria-label="Main navigation">
          <a className="active" href="#overview">Workspace</a>
          <a href="#repository-intelligence">Repository</a>
          <a href="#task-planner">Task planner</a>
        </nav>
        <div className="topbar-right">
          <Badge tone={backend === "connected" ? "good" : backend === "offline" ? "warning" : "neutral"}>
            {backend === "connected" ? "API connected" : backend === "offline" ? "API offline" : "Connecting"}
          </Badge>
          <span className="avatar" aria-label="Local workspace">DR</span>
        </div>
      </header>

      <main id="overview" className="main-content">
        <section className="welcome-row" aria-labelledby="page-title">
          <div>
            <p className="eyebrow">ENGINEERING HANDOFF WORKSPACE <span>·</span> PHASE 5A</p>
            <h1 id="page-title">Good work starts with <em>context.</em></h1>
            <p className="welcome-copy">Understand a repository. Shape a plan. Keep every next step grounded in evidence.</p>
          </div>
          <div className="backend-summary" aria-live="polite">
            <span className={`status-orb ${backend}`} />
            <div><span>Backend status</span><strong title={backendMessage}>{backendMessage}</strong></div>
          </div>
        </section>

        <section className="workspace-toolbar" aria-label="Workspace configuration">
          <div className="toolbar-label"><span className="toolbar-icon">⌘</span><div><strong>Active repository</strong><small>Authorized workspace ID</small></div></div>
          {configuredRepositories.length > 0 ? (
            <label className="select-wrap">
              <span className="sr-only">Select configured repository</span>
              <select value={repositoryId} onChange={(event) => onRepositoryChange(event.target.value)}>
                {configuredRepositories.map((id) => <option key={id} value={id}>{id}</option>)}
              </select><span aria-hidden="true">⌄</span>
            </label>
          ) : <p className="config-hint">No repository IDs configured. Set <code>NEXT_PUBLIC_REPOSITORY_IDS</code> in <code>frontend/.env.local</code>.</p>}
          <div className="provider-summary"><span className="provider-icon">✳</span><div><small>Inference provider</small><strong>{providerLabel}</strong><small>{inferenceStateLabel}</small></div></div>
        </section>

        {isMock && <div className="mock-banner" role="status"><span aria-hidden="true">✳</span><div><strong>MOCK MODE</strong><span>Simulated inference for development testing. This result was not generated by NVIDIA Nemotron.</span></div></div>}
        {error && <div className="error-banner" role="alert"><strong>Request failed</strong><span>{error}</span><button type="button" onClick={() => setError(null)} aria-label="Dismiss error">×</button></div>}

        <div className="section-heading"><div><p className="eyebrow">YOUR ENGINEERING TOOLKIT</p><h2>Explore &amp; plan</h2></div><span className="local-note"><span aria-hidden="true">●</span> Local analysis · Read-only</span></div>

        <div className="work-grid">
          <section id="repository-intelligence" className="panel repository-panel" aria-labelledby="repository-title">
            <div className="panel-heading">
              <div className="panel-icon repo-icon" aria-hidden="true">⌕</div>
              <div className="panel-title"><div className="panel-kicker">01 <span>·</span> UNDERSTAND</div><h3 id="repository-title">Repository intelligence</h3><p>Map modules, symbols and dependencies without running project code.</p></div>
            </div>
            <div className="panel-action-row"><span className="privacy-note"><span>◉</span> Static analysis only</span><button className="button button-primary" type="button" onClick={runAnalysis} disabled={!repositoryId || analysisBusy || backend !== "connected"}>
              {analysisBusy ? <><span className="spinner" /> Analyzing</> : <>Analyze repository <span aria-hidden="true">↗</span></>}
            </button></div>

            {!repositoryId && <EmptyState title="Choose an authorized repository" detail="Configure a repository ID for the dashboard before running analysis." />}
            {repositoryId && backend === "offline" && !analysis && <EmptyState title="Backend is not responding" detail="Start FastAPI, then refresh the dashboard or try again." />}
            {repositoryId && !analysis && !analysisBusy && backend !== "offline" && <EmptyState title="Your repository map starts here" detail="Run an analysis to see source files, modules, symbols, imports and warnings." />}
            {analysisBusy && <div className="loading-block" role="status"><span className="spinner spinner-large" /><span>Reading repository structure…</span></div>}
            {analysis && <div className="analysis-results" aria-live="polite">
              <div className="metrics-grid">
                <Metric label="Files" value={analysis.summary.file_count} />
                <Metric label="Python modules" value={analysis.summary.module_count} />
                <Metric label="Functions" value={analysis.summary.function_count} />
                <Metric label="Tests" value={analysis.summary.test_file_count} />
              </div>
              <div className="result-meta"><Badge tone="good">Analysis complete</Badge><span>{analysis.summary.class_count} classes</span><span>{analysis.summary.import_count} imports</span><span>{analysis.summary.dependency_count} dependencies</span><span>{analysis.summary.duration_ms} ms</span></div>
              <div className="data-section"><div className="data-section-heading"><h4>Discovered modules</h4><span>{analysis.modules.length}</span></div>
                {analysis.modules.length ? <div className="module-list">{analysis.modules.map((module) => <div className="module-row" key={module.path}><span className="file-glyph">PY</span><div className="module-name"><strong>{module.name}</strong><small>{module.path}</small></div><span className="module-count">{module.functions} fn</span><span className="module-count">{module.classes} cls</span></div>)}</div> : <p className="subtle-empty">No Python modules found.</p>}
              </div>
              <details className="inspect-details"><summary>Functions, classes &amp; source references <span>{analysis.functions.length + analysis.classes.length}</span></summary>
                <div className="symbol-list">{analysis.functions.map((item) => <div className="symbol-row" key={`fn-${item.source.path}-${item.source.line}`}><span>ƒ</span><strong>{item.qualified_name}</strong><Reference path={item.source.path} line={item.source.line} /></div>)}{analysis.classes.map((item) => <div className="symbol-row" key={`class-${item.source.path}-${item.source.line}`}><span>C</span><strong>{item.qualified_name}</strong><Reference path={item.source.path} line={item.source.line} /></div>)}</div>
              </details>
              <details className="inspect-details"><summary>Imports &amp; dependency manifests <span>{analysis.imports.length + analysis.dependency_manifests.length}</span></summary>
                <div className="compact-list">{analysis.imports.map((item, index) => <div key={`${item.source_path}-${item.line}-${index}`}><Reference path={item.source_path} line={item.line} /><span> imports </span><code>{item.imported_module}{item.imported_names.length ? ` · ${item.imported_names.join(", ")}` : ""}</code></div>)}{analysis.dependency_manifests.map((manifest) => <div className="manifest-row" key={manifest.path}><strong>{manifest.path}</strong><span>{manifest.dependencies.length ? manifest.dependencies.join(", ") : "No dependencies listed"}</span></div>)}</div>
              </details>
              <details className="inspect-details"><summary>Tests, configuration &amp; warnings <span>{analysis.test_files.length + analysis.warnings.length}</span></summary>
                <div className="compact-list">{analysis.test_files.map((path) => <div key={path}><span className="test-mark">✓</span><code>{path}</code></div>)}{analysis.configuration_files.map((path) => <div key={path}><span className="config-mark">⚙</span><code>{path}</code></div>)}{analysis.warnings.map((warning, index) => <div className="warning-row" key={`${warning.code}-${index}`}><span className="warning-mark">!</span><strong>{warning.code}</strong><span>{warning.message}</span>{warning.path && <code>{warning.path}{warning.line ? `:${warning.line}` : ""}</code>}</div>)}{analysis.test_files.length + analysis.configuration_files.length + analysis.warnings.length === 0 && <p className="subtle-empty">No tests, configuration files or warnings reported.</p>}</div>
              </details>
            </div>}
          </section>

          <section id="task-planner" className="panel planner-panel" aria-labelledby="planner-title">
            <div className="panel-heading">
              <div className="panel-icon plan-icon" aria-hidden="true">↗</div>
              <div className="panel-title"><div className="panel-kicker">02 <span>·</span> MAKE A PLAN</div><h3 id="planner-title">Engineering task planner</h3><p>Turn a clear engineering request into a reviewable, evidence-backed plan.</p></div>
            </div>
            <form className="task-form" onSubmit={submitPlan}>
              <label htmlFor="task-description">What needs attention?</label>
              <textarea id="task-description" value={taskDescription} onChange={(event) => setTaskDescription(event.target.value)} minLength={10} maxLength={4000} required placeholder="e.g. Fix the division by zero defect in the calculator" />
              <div className="form-footer"><span>{taskDescription.length}/4,000 characters</span><button className="button button-dark" type="submit" disabled={!repositoryId || planningBusy || backend !== "connected" || taskDescription.trim().length < 10}>
                {planningBusy ? <><span className="spinner spinner-light" /> Planning</> : <>Generate plan <span aria-hidden="true">→</span></>}
              </button></div>
            </form>
            {!plan && !planningBusy && <EmptyState title="A plan you can inspect" detail="Plans include proposed steps, source evidence, risks and tests. Nothing is changed or executed." />}
            {planningBusy && <div className="loading-block" role="status"><span className="spinner spinner-large" /><span>Preparing repository context…</span></div>}
            {plan && <PlanResult plan={plan} />}
            {plan?.status === "planned" && plan.unsupported_references.length === 0 && /division by zero/i.test(plan.task_description) && !proposal && <div className="proposal-action"><p>The server verifies the plan and current analysis snapshot, then creates only the fixed calculator transformation. The source file remains unchanged. The diff is deterministic; the planning provider is shown separately.</p><button className="button button-primary" type="button" onClick={generateProposal} disabled={proposalBusy || backend !== "connected"}>{proposalBusy ? <><span className="spinner" /> Preparing proposal</> : <>Generate code proposal <span aria-hidden="true">→</span></>}</button></div>}
            {proposal && <ProposalResult proposal={proposal} />}
            {proposal && <ReviewPanel proposal={proposal} status={reviewStatus} history={reviewHistory} reviewerIdentifier={reviewerIdentifier} setReviewerIdentifier={setReviewerIdentifier} justification={reviewJustification} setJustification={setReviewJustification} outstandingQuestions={outstandingQuestions} setOutstandingQuestions={setOutstandingQuestions} busy={reviewBusy} onDecision={recordReview} />}
            {proposal && <RuntimeValidationPanel proposal={proposal} readiness={sandboxReadiness} evidence={runtimeEvidence} authorizer={executionAuthorizer} setAuthorizer={setExecutionAuthorizer} purpose={executionPurpose} setPurpose={setExecutionPurpose} busy={runtimeBusy} onRequest={requestRuntimeRun} />}
            {proposal && <section className="handoff-section" aria-labelledby="handoff-heading"><div className="handoff-title-row"><div><p className="eyebrow">ENGINEERING CONTEXT</p><h4 id="handoff-heading">Engineering handoff report</h4></div><button className="button button-dark" type="button" onClick={buildHandoff} disabled={handoffBusy || backend !== "connected"}>{handoffBusy ? "Generating…" : handoff ? "Refresh report" : "Generate report"}</button></div>{handoff && <HandoffResult report={handoff} markdownStatus={markdownStatus} onCopy={copyHandoffMarkdown} onDownload={downloadHandoffMarkdown} />}</section>}
          </section>
        </div>

        <section className="roadmap-panel" aria-labelledby="roadmap-title">
          <div className="roadmap-heading"><div><p className="eyebrow">ON THE HORIZON</p><h2 id="roadmap-title">More ways to move work forward</h2></div><Badge tone="muted">Coming later</Badge></div>
          <div className="roadmap-items"><RoadmapItem number="03" title="Safe code proposals" detail="A fixed calculator scenario produces a static, review-only diff." available /><RoadmapItem number="04" title="Autonomous execution" detail="Isolated validation with explicit human approval." /><RoadmapItem number="05" title="Team handoffs" detail="Share context and decisions across your team." /></div>
          <p className="unavailable-note">Autonomous execution and team handoffs are not available in this build.</p>
        </section>

        <footer className="footer"><div className="footer-brand"><BrandMark /><span>devrelayai</span></div><span>Built for thoughtful engineering handoffs.</span><span className="footer-version">LOCAL WORKSPACE · 0.1.0</span></footer>
      </main>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="metric"><strong>{value.toLocaleString()}</strong><span>{label}</span></div>;
}

function PlanResult({ plan }: { plan: TaskPlan }) {
  const statusTone = plan.status === "planned" ? "good" : "warning";
  const diagnostics = plan.inference_diagnostics;
  const usage = diagnostics?.usage;
  return <div className="plan-result" aria-live="polite">
    {plan.is_mock && <div className="mock-banner mock-banner-inline" role="status"><span aria-hidden="true">✳</span><div><strong>MOCK MODE — Simulated inference for development testing.</strong><span>This response was not generated by NVIDIA Nemotron.</span></div></div>}
    <div className="plan-result-heading"><div><Badge tone={statusTone}>{plan.status.replaceAll("_", " ")}</Badge><p className="plan-provider">Provider: {plan.provider}{plan.is_mock ? " · mock" : ""}</p></div><span className="approval-pill">{plan.human_approval_required ? "Human approval required" : "Approval not required"}</span></div>
    {diagnostics && <section className="inference-diagnostics" aria-label="Inference diagnostics">
      <strong>{plan.is_mock ? "Deterministic mock result — not AI-generated." : plan.unsupported_references.length > 0 ? "AI-generated plan; verified evidence is listed separately. Rejected citations are unverified." : "AI-generated planning result; source evidence was validated locally."}</strong>
      <div><span>Model: <code>{diagnostics.model}</code>{!diagnostics.model_reported_by_provider && " (requested; provider omitted model identity)"}</span>
        <span>Completion: {diagnostics.completion_status}{diagnostics.finish_reason ? ` · ${diagnostics.finish_reason}` : ""}</span>
        {diagnostics.latency_ms !== null && <span>Latency: {diagnostics.latency_ms} ms</span>}
        {usage && <span>Tokens: input {usage.input_tokens ?? "n/a"} · output {usage.output_tokens ?? "n/a"} · reasoning {usage.reasoning_tokens ?? "n/a"} · total {usage.total_tokens ?? "n/a"}</span>}
      </div>
    </section>}
    {plan.status === "unsupported" && <EmptyState title="No plan was generated" detail={plan.assumptions[0] ?? "This task is outside the supported scenarios."} />}
    {plan.status === "insufficient_context" && <div className="context-note"><strong>More context is needed</strong><p>{plan.assumptions.join(" ") || "Some of the returned evidence could not be verified against repository analysis."}</p>{plan.unsupported_references.length > 0 && <><strong>Unverified citations — rejected by source validation</strong><div className="reference-chips">{plan.unsupported_references.map((reference) => <code key={reference}>{reference}</code>)}</div></>}</div>}
    {plan.relevant_files.length > 0 && <div className="data-section"><div className="data-section-heading"><h4>Relevant repository files</h4><span>{plan.relevant_files.length}</span></div><div className="file-chips">{plan.relevant_files.map((path) => <code key={path}>{path}</code>)}</div></div>}
    {plan.implementation_steps.length > 0 && <div className="data-section"><div className="data-section-heading"><h4>Proposed steps</h4><span>{plan.implementation_steps.length}</span></div><ol className="step-list">{plan.implementation_steps.map((step) => <li key={step.step}><span className="step-number">{String(step.step).padStart(2, "0")}</span><div><p>{step.description}</p>{step.source_references.length > 0 && <div className="reference-chips">{step.source_references.map((ref) => <Reference key={`${ref.path}:${ref.line}`} path={ref.path} line={ref.line} />)}</div>}</div></li>)}</ol></div>}
    {plan.source_references.length > 0 && <div className="data-section"><div className="data-section-heading"><h4>Supporting evidence</h4><span>{plan.source_references.length}</span></div><div className="reference-chips">{plan.source_references.map((ref) => <Reference key={`${ref.path}:${ref.line}`} path={ref.path} line={ref.line} />)}</div></div>}
    <div className="plan-bottom-grid">{plan.risks.length > 0 && <div className="plan-list"><h4>Risks &amp; assumptions</h4><ul>{[...plan.risks, ...plan.assumptions].map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div>}{plan.validation_requirements.length > 0 && <div className="plan-list"><h4>Validation</h4><ul>{plan.validation_requirements.map((item) => <li key={item}>{item}</li>)}</ul></div>}</div>
    {plan.expected_code_changes.length > 0 && <div className="change-notice"><span aria-hidden="true">◇</span><div><strong>Proposed changes only</strong>{plan.expected_code_changes.map((change) => <p key={change.path}><code>{change.path}</code> · {change.description}</p>)}</div></div>}
    {plan.execution_status === "not_started" && <p className="execution-state"><span /> Execution has not started</p>}
  </div>;
}

function RoadmapItem({ number, title, detail, available = false }: { number: string; title: string; detail: string; available?: boolean }) {
  return <div className="roadmap-item"><span>{number}</span><div><strong>{title}</strong><p>{detail}</p></div><Badge tone={available ? "good" : "muted"}>{available ? "Available" : "Unavailable"}</Badge></div>;
}

function ProposalResult({ proposal }: { proposal: CodeChangeProposal }) {
  return <section className="proposal-result" aria-labelledby="proposal-title" aria-live="polite">
    <div className="proposal-heading"><div><p className="eyebrow">REVIEW ONLY · {proposal.lifecycle_state.replaceAll("_", " ")}</p><h4 id="proposal-title">Code change proposal</h4></div><Badge tone="good">Static checks passed</Badge></div>
    <p className="proposal-task"><strong>Task:</strong> {proposal.task_description}</p>
    <p className="proposal-summary">{proposal.proposed_change_summary}</p>
    <div className="proposal-meta"><span>Plan provider: {proposal.originating_plan_provider}</span><span>Proposal generator: deterministic allowlist</span><span>Transformation: {proposal.transformation_id}</span><span>Risk: {proposal.risk_classification}</span><span>Human approval required</span></div>
    {proposal.target_files.map((file) => <div className="proposal-target" key={file.path}><strong>Target</strong><code>{file.path}:{file.source_reference.line}</code><small>Source SHA-256: <code>{file.original_sha256}</code></small></div>)}
    <div className="proposal-findings"><h5>Static validation findings</h5><ul>{proposal.validation_findings.map((finding) => <li key={finding.check}><Badge tone={finding.status === "passed" ? "good" : "muted"}>{finding.status}</Badge><span>{finding.detail}</span></li>)}</ul></div>
    <h5>Unified diff</h5><pre className="proposal-diff"><code>{proposal.unified_diff}</code></pre>
    <div className="runtime-not-run"><strong>Runtime validation: not run</strong><p>{proposal.runtime_validation_reason}</p></div>
    <p className="proposal-safety">Mock-generated proposal. No files were changed, approved, applied, or executed.</p>
  </section>;
}

function ReviewPanel({ proposal, status, history, reviewerIdentifier, setReviewerIdentifier, justification, setJustification, outstandingQuestions, setOutstandingQuestions, busy, onDecision }: {
  proposal: CodeChangeProposal;
  status: LocalReviewStatus | null;
  history: ReviewHistory | null;
  reviewerIdentifier: string;
  setReviewerIdentifier: (value: string) => void;
  justification: string;
  setJustification: (value: string) => void;
  outstandingQuestions: string;
  setOutstandingQuestions: (value: string) => void;
  busy: boolean;
  onDecision: (decision: ReviewDecision) => void;
}) {
  const canReview = status?.enabled === true && proposal.lifecycle_state === "awaiting_review";
  const reviewCompleted = Boolean(history?.reviews?.length) || ["review_approved", "changes_requested", "rejected"].includes(proposal.lifecycle_state);
  const identifierError = reviewerIdentifierError(reviewerIdentifier);
  return <section className="review-panel" aria-labelledby="review-heading">
    <div className="handoff-title-row"><div><p className="eyebrow">HUMAN-IN-THE-LOOP</p><h4 id="review-heading">Human review</h4></div><Badge tone={canReview || reviewCompleted ? "good" : "muted"}>{reviewCompleted ? "Review Completed" : canReview ? "Local review enabled" : "Review Unavailable"}</Badge></div>
    <div className="identity-warning" role="note"><strong>Local development only.</strong> Reviewer identifiers are unverified labels. An approval means accepted for further consideration; it does not apply or execute code.</div>
    {!status?.enabled && <p className="review-disabled">Review decisions are disabled. Set <code>ENABLE_LOCAL_REVIEWS=true</code> in development and restart FastAPI.</p>}
    {canReview && <div className="review-form">
      <label htmlFor="reviewer-id">Local reviewer label</label>
      <input id="reviewer-id" value={reviewerIdentifier} maxLength={64} onChange={(event) => setReviewerIdentifier(event.target.value)} autoComplete="off" aria-invalid={Boolean(identifierError)} aria-describedby="reviewer-id-format reviewer-id-error" />
      <small id="reviewer-id-format">1–64 characters; begin with a letter or number, then use letters, numbers, periods, underscores, or hyphens. Example: <code>demo_reviewer</code>. Spaces and credential-like values are not accepted.</small>
      {identifierError && <small id="reviewer-id-error" className="reviewer-input-error" role="alert">{identifierError}</small>}
      <label htmlFor="review-justification">Decision justification <span>Required</span></label>
      <textarea id="review-justification" value={justification} maxLength={2000} onChange={(event) => setJustification(event.target.value)} placeholder="Explain why this decision is appropriate." />
      <label htmlFor="review-questions">Outstanding questions <span>Optional, one per line</span></label>
      <textarea id="review-questions" value={outstandingQuestions} maxLength={3600} onChange={(event) => setOutstandingQuestions(event.target.value)} placeholder="Questions for the next engineer" />
      <div className="review-actions">
        <button className="button button-primary" type="button" onClick={() => onDecision("approve")} disabled={busy || Boolean(identifierError) || !justification.trim()}>Approve for consideration</button>
        <button className="button button-dark" type="button" onClick={() => onDecision("request_changes")} disabled={busy || Boolean(identifierError) || !justification.trim()}>Request changes</button>
        <button className="button button-reject" type="button" onClick={() => onDecision("reject")} disabled={busy || Boolean(identifierError) || !justification.trim()}>Reject proposal</button>
      </div>
      <small>Decision uses proposal version {proposal.version} and its source and diff hashes.</small>
    </div>}
    {history && <div className="review-history"><h5>Decision and audit history</h5>{history.reviews?.length ? history.reviews.map((review) => <article key={review.review_id}><strong>{review.decision.replaceAll("_", " ")} · {review.proposal_lifecycle_state.replaceAll("_", " ")}</strong><small>{review.reviewer_identifier} (unverified) · {new Date(review.timestamp).toLocaleString()}</small><p>{review.justification}</p>{review.outstanding_questions.length > 0 && <ul>{review.outstanding_questions.map((question) => <li key={question}>{question}</li>)}</ul>}</article>) : <p>No decisions recorded.</p>}{(history.audit_events ?? []).filter((event) => event.outcome === "rejected").map((event) => <article className="audit-rejection" key={event.event_id}><strong>Review submission rejected</strong><small>{event.reviewer_identifier} (unverified) · {new Date(event.timestamp).toLocaleString()}</small><p>{event.failure_reason ?? "The review could not be recorded."}</p></article>)}</div>}
  </section>;
}

function RuntimeValidationPanel({ proposal, readiness, evidence, authorizer, setAuthorizer, purpose, setPurpose, busy, onRequest }: {
  proposal: CodeChangeProposal;
  readiness: SandboxReadiness | null;
  evidence: RuntimeValidationEvidence | null;
  authorizer: string;
  setAuthorizer: (value: string) => void;
  purpose: string;
  setPurpose: (value: string) => void;
  busy: boolean;
  onRequest: () => void;
}) {
  const eligible = proposal.lifecycle_state === "review_approved";
  const validAuthorizer = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(authorizer.trim());
  return <section className="runtime-validation-panel" aria-labelledby="runtime-validation-heading">
    <div className="handoff-title-row"><div><p className="eyebrow">SEPARATE EXECUTION AUTHORIZATION</p><h4 id="runtime-validation-heading">Isolated runtime validation</h4></div><Badge tone={readiness?.available ? "good" : "muted"}>{readiness?.available ? "Sandbox ready" : readiness?.enabled ? "Sandbox unavailable" : "Execution disabled"}</Badge></div>
    <div className="identity-warning" role="note"><strong>Review approval does not authorize execution.</strong> Each run requires a separate purpose and an unverified local authorizer label. The original repository will remain unchanged.</div>
    <p><strong>Selected test suite:</strong> <code>calculator_unit_tests</code> · command ID <code>calculator_pytest_suite_v1</code></p>
    <p><strong>Source SHA-256:</strong> <code>{proposal.target_files[0].original_sha256}</code></p>
    <p><strong>Diff SHA-256:</strong> <code>{proposal.diff_sha256}</code></p>
    {!readiness && <p role="status">Sandbox readiness could not be read. Runtime validation remains not run.</p>}
    {readiness && <><p><strong>Readiness:</strong> {readiness.status === "disabled" ? "Feature flag disabled." : readiness.available ? "All checks passed." : "Required isolation checks failed; no code was run."}</p><ul className="sandbox-checks">{readiness.checks.map((check) => <li key={check.name}><strong>{check.name}:</strong> {check.status} — {check.detail}</li>)}</ul>{readiness.limitations.map((item) => <small className="sandbox-limitation" key={item}>{item}</small>)}</>}
    {readiness?.enabled && eligible && !evidence && <div className="runtime-authorization-form">
      <label htmlFor="execution-authorizer">Execution authorizer label</label>
      <input id="execution-authorizer" value={authorizer} maxLength={64} onChange={(event) => setAuthorizer(event.target.value)} autoComplete="off" />
      <small>Unverified local-development identity; use a label such as <code>local_authorizer</code>.</small>
      <label htmlFor="execution-purpose">Purpose for this one-time validation</label>
      <textarea id="execution-purpose" value={purpose} maxLength={300} onChange={(event) => setPurpose(event.target.value)} placeholder="Explain why this reviewed proposal needs isolated validation." />
      <button className="button button-dark" type="button" onClick={onRequest} disabled={busy || !validAuthorizer || purpose.trim().length < 10}>{busy ? "Recording authorization…" : "Authorize one validation request"}</button>
    </div>}
    {readiness?.enabled && !eligible && !evidence && <p>Runtime validation is available only for a proposal in the review-approved state.</p>}
    {evidence && <div className="runtime-evidence" aria-live="polite">
      <h5>Execution evidence</h5><p><strong>Outcome:</strong> {evidence.status}</p><p>{evidence.sandbox_summary}</p>
      <p><strong>Evidence ID:</strong> <code>{evidence.evidence_id}</code></p><p><strong>Authorizer:</strong> {evidence.authorizer_identifier} (unverified local-development label) · purpose: {evidence.authorization_purpose}</p>
      <p><strong>Test command ID:</strong> <code>{evidence.test_command_id}</code> · <strong>Exit code:</strong> {evidence.exit_code ?? "not run"} · <strong>Duration:</strong> {evidence.duration_ms === null ? "not run" : `${evidence.duration_ms} ms`}</p>
      {evidence.failure_reason && <p><strong>Reason:</strong> {evidence.failure_reason}</p>}
      {evidence.test_results.length > 0 && <ul>{evidence.test_results.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>}
      {evidence.stdout && <details><summary>Captured stdout (bounded)</summary><pre>{evidence.stdout}</pre></details>}
      {evidence.stderr && <details><summary>Captured stderr (bounded)</summary><pre>{evidence.stderr}</pre></details>}
      <p><strong>Original repository modified:</strong> no · <strong>Patch applied to original:</strong> no</p>
    </div>}
    <p className="runtime-not-run"><strong>No host fallback.</strong> If a trusted sandbox is unavailable, the outcome remains <code>sandbox_unavailable</code>; repository tests are never run directly on Windows.</p>
  </section>;
}

function HandoffResult({ report, markdownStatus, onCopy, onDownload }: { report: HandoffReport; markdownStatus: string; onCopy: () => void; onDownload: () => void }) {
  return <div className="handoff-result" aria-live="polite">
    <div className="handoff-report-toolbar"><Badge tone="good">Deterministic handoff · {report.task.planning_provider} plan</Badge><div><button className="button button-dark" type="button" onClick={onCopy}>Copy Markdown</button><button className="button button-primary" type="button" onClick={onDownload}>Download Markdown</button></div></div>
    {markdownStatus && <p className="markdown-status" role="status">{markdownStatus}</p>}
    <h5>Project and task context</h5><p>{report.task.objective}</p><p>Planning provider: {report.task.planning_provider}. The proposal itself is generated by the fixed deterministic allowlist.</p><p>{report.task.current_progress}</p>
    <h5>Verified technical context</h5><ul>{report.technical_understanding.verified_context.map((item) => <li key={item}>{item}</li>)}</ul>
    <p><strong>Relevant files:</strong> {report.task.relevant_files.join(", ")}</p>
    <h5>Planned implementation steps</h5>{report.task.planned_steps.length ? <ol>{report.task.planned_steps.map((step, index) => <li key={`${index}-${step}`}>{step.replace(/^\d+\.\s*/, "")}</li>)}</ol> : <p>None recorded</p>}
    <h5>Planned validation</h5>{report.task.planned_validation_requirements.length ? <ul>{report.task.planned_validation_requirements.map((item) => <li key={item}>{item}</li>)}</ul> : <p>None recorded</p>}
    <p><strong>Modules:</strong> {report.technical_understanding.relevant_modules.map((module) => `${module.name} (${module.path})`).join(", ") || "None found"}</p>
    <p><strong>Functions:</strong> {report.technical_understanding.relevant_functions.join(", ") || "None found"}</p>
    <p><strong>Classes:</strong> {report.technical_understanding.relevant_classes.join(", ") || "None found"}</p>
    <p><strong>Imports:</strong> {report.technical_understanding.relevant_imports.join("; ") || "None found"}</p>
    <p><strong>Dependency manifests:</strong> {report.technical_understanding.dependency_manifests.join("; ") || "None found"}</p>
    {report.technical_understanding.analysis_warnings.length > 0 && <><h5>Analysis warnings</h5><ul>{report.technical_understanding.analysis_warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></>}
    <h5>Proposed change</h5><p>{report.proposed_change.summary}</p><p><strong>Originating plan provider:</strong> {report.proposed_change.originating_plan_provider} · <strong>Allowlisted transformation:</strong> {report.proposed_change.transformation_id}</p><p><strong>Source revision:</strong> {report.proposed_change.source_revision_status}</p>
    <ul>{report.proposed_change.target_files.map((target) => <li key={target.path}>{target.path}:{target.source_reference.line} · SHA-256 {target.original_sha256}</li>)}</ul>
    <p><strong>Diff SHA-256:</strong> {report.proposed_change.diff_sha256}</p>
    <h5>Validation</h5><p><strong>Static checks</strong></p><ul>{report.validation_and_risks.static_checks.length ? report.validation_and_risks.static_checks.map((finding) => <li key={finding.check}>{finding.check}: {finding.status} — {finding.detail}</li>) : <li>None recorded</li>}</ul>
    <p><strong>Runtime tests:</strong> {report.validation_and_risks.runtime_tests_status} — {report.validation_and_risks.runtime_tests_reason}</p>
    <p><strong>Risks:</strong> {report.validation_and_risks.risks.join("; ") || "None recorded"}</p>
    <p><strong>Assumptions:</strong> {report.validation_and_risks.assumptions.join("; ") || "None recorded"}</p>
    <p><strong>Unresolved dependencies:</strong> {report.validation_and_risks.unresolved_dependencies.join("; ") || "None recorded"}</p>
    <p><strong>Missing evidence:</strong> {report.validation_and_risks.unsupported_evidence.join("; ") || "None recorded"}</p>
    <h5>Isolated runtime evidence</h5><p>{report.runtime_execution.sandbox_summary}</p><p><strong>Test case:</strong> {report.runtime_execution.test_case} · <strong>Command ID:</strong> {report.runtime_execution.test_command_id} · <strong>Exit:</strong> {report.runtime_execution.exit_code ?? "not run"} · <strong>Duration:</strong> {report.runtime_execution.duration_ms === null ? "not run" : `${report.runtime_execution.duration_ms} ms`}</p>
    <p><strong>Evidence ID:</strong> {report.runtime_execution.evidence_id ?? "None"}</p><p><strong>Runtime source hash:</strong> {report.runtime_execution.source_sha256} · <strong>Runtime diff hash:</strong> {report.runtime_execution.diff_sha256}</p>
    {report.runtime_execution.test_results.length > 0 && <ul>{report.runtime_execution.test_results.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>}
    <ul>{report.runtime_execution.remaining_work.map((item) => <li key={item}>{item}</li>)}</ul>
    <h5>Outstanding questions</h5><ul>{report.outstanding_questions.map((question) => <li key={question}>{question}</li>)}</ul>
    <h5>Human decisions</h5>{report.human_decisions.length ? report.human_decisions.map((decision) => <article className="handoff-decision" key={decision.review_id}><strong>{decision.decision.replaceAll("_", " ")}</strong><small>{decision.reviewer_identifier} (unverified local-development label) · {new Date(decision.timestamp).toLocaleString()}</small><p>{decision.justification}</p></article>) : <p>No human decision recorded.</p>}
    <h5>Next engineer actions</h5><ul>{report.next_engineer_actions.map((action, index) => <li key={`${index}-${action.action}`}>{action.action}{action.required_approval ? " (further approval required)" : ""}</li>)}</ul>
    <p className="provenance-note">{report.provenance_note}</p>
  </div>;
}
