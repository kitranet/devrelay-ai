"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { analyzeRepository, checkBackend, createProposal, planTask } from "@/lib/api";
import type { CodeChangeProposal, RepositoryAnalysis, TaskPlan } from "@/lib/types";

type BackendState = "checking" | "connected" | "offline";

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
  const [taskDescription, setTaskDescription] = useState("");
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [planningBusy, setPlanningBusy] = useState(false);
  const [proposalBusy, setProposalBusy] = useState(false);
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

  const providerLabel = useMemo(() => {
    if (!plan) return "Reported with first plan";
    return plan.is_mock ? "Mock provider" : "Nebius Token Factory";
  }, [plan]);

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
      if (nextPlan.status === "planned") setProposal(null);
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
      setProposal(await createProposal(repositoryId, plan.task_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Proposal generation failed.");
    } finally {
      setProposalBusy(false);
    }
  }

  function onRepositoryChange(value: string) {
    setRepositoryId(value);
    setAnalysis(null);
    setPlan(null);
    setProposal(null);
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
            <p className="eyebrow">ENGINEERING HANDOFF WORKSPACE <span>·</span> PHASE 4B</p>
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
          <div className="provider-summary"><span className="provider-icon">✳</span><div><small>Inference provider</small><strong>{providerLabel}</strong></div></div>
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
            {plan?.status === "planned" && plan.is_mock && /division by zero/i.test(plan.task_description) && !proposal && <div className="proposal-action"><p>This fixed mock scenario can produce a review-only patch. The source file will remain unchanged.</p><button className="button button-primary" type="button" onClick={generateProposal} disabled={proposalBusy || backend !== "connected"}>{proposalBusy ? <><span className="spinner" /> Preparing proposal</> : <>Generate code proposal <span aria-hidden="true">→</span></>}</button></div>}
            {proposal && <ProposalResult proposal={proposal} />}
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
  return <div className="plan-result" aria-live="polite">
    {plan.is_mock && <div className="mock-banner mock-banner-inline" role="status"><span aria-hidden="true">✳</span><div><strong>MOCK MODE — Simulated inference for development testing.</strong><span>This response was not generated by NVIDIA Nemotron.</span></div></div>}
    <div className="plan-result-heading"><div><Badge tone={statusTone}>{plan.status.replaceAll("_", " ")}</Badge><p className="plan-provider">Provider: {plan.provider}{plan.is_mock ? " · mock" : ""}</p></div><span className="approval-pill">{plan.human_approval_required ? "Human approval required" : "Approval not required"}</span></div>
    {plan.status === "unsupported" && <EmptyState title="No plan was generated" detail={plan.assumptions[0] ?? "This task is outside the supported scenarios."} />}
    {plan.status === "insufficient_context" && <div className="context-note"><strong>More context is needed</strong><p>{plan.assumptions.join(" ") || "Some of the returned evidence could not be verified against repository analysis."}</p>{plan.unsupported_references.length > 0 && <div className="reference-chips">{plan.unsupported_references.map((reference) => <code key={reference}>{reference}</code>)}</div>}</div>}
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
    <div className="proposal-meta"><span>Provider: mock</span><span>Risk: {proposal.risk_classification}</span><span>Human approval required</span></div>
    {proposal.target_files.map((file) => <div className="proposal-target" key={file.path}><strong>Target</strong><code>{file.path}:{file.source_reference.line}</code><small>Source SHA-256: <code>{file.original_sha256}</code></small></div>)}
    <div className="proposal-findings"><h5>Static validation findings</h5><ul>{proposal.validation_findings.map((finding) => <li key={finding.check}><Badge tone={finding.status === "passed" ? "good" : "muted"}>{finding.status}</Badge><span>{finding.detail}</span></li>)}</ul></div>
    <h5>Unified diff</h5><pre className="proposal-diff"><code>{proposal.unified_diff}</code></pre>
    <div className="runtime-not-run"><strong>Runtime validation: not run</strong><p>{proposal.runtime_validation_reason}</p></div>
    <p className="proposal-safety">Mock-generated proposal. No files were changed, approved, applied, or executed.</p>
  </section>;
}
