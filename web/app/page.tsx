"use client";

import { useState } from "react";

const signals = [
  { time: "00:04:14", title: "Synthetic checkout returned HTTP 503", source: "Live checkout probe", tone: "critical" },
  { time: "00:04:14", title: "Fault-mode gauge reported errors", source: "Prometheus via OpenTelemetry", tone: "change" },
  { time: "00:04:14", title: "Recovery verified: mode none, health 200", source: "Governed Action Broker", tone: "healthy" },
];

const users = [
  { name: "Sai Demo", initials: "SD", role: "Incident commander", canApprove: true, active: true },
  { name: "Alex Observer", initials: "AO", role: "Read-only observer", canApprove: false, active: true },
  { name: "Former Engineer", initials: "FE", role: "Disabled platform lead", canApprove: false, active: false },
];

const capabilities = [
  { label: "OBSERVE", title: "Telemetry that actually runs", body: "Checkout → OpenTelemetry Collector → Prometheus → agent-generated alerts and Grafana dashboard." },
  { label: "OPERATE", title: "Agents with a hard boundary", body: "Read-only investigation is automatic. Mutations require scope policy, active role, signed approval, verification, and audit." },
  { label: "PROVISION", title: "Provider-native foundations", body: "Private EKS and AKS modules preserve native identity, encryption, networking, logging, and availability controls." },
  { label: "RECOVER", title: "Failure is part of the test", body: "A real Pod is deleted in Kind. Replacement UID and full 2/2 readiness are required within 120 seconds." },
];

export default function Home() {
  const [userIndex, setUserIndex] = useState(0);
  const [reviewing, setReviewing] = useState(false);
  const [incidentState, setIncidentState] = useState<"active" | "recovering" | "resolved">("active");
  const user = users[userIndex];

  function switchUser() { setUserIndex((userIndex + 1) % users.length); }
  function approveRecovery() {
    setIncidentState("recovering");
    setReviewing(false);
    window.setTimeout(() => setIncidentState("resolved"), 1600);
  }

  return (
    <main className="shell">
      <aside className="rail">
        <div className="brand"><span className="brandMark">S</span><span>SENTINEL / SRE</span></div>
        <nav aria-label="Portfolio sections">
          <a className="active" href="#command-center">Command center</a>
          <a href="#architecture">Architecture</a>
          <a href="#evidence">Evidence <span className="badge">12</span></a>
          <a href="https://github.com/justinmail735-eng/Sai-SRE-AI_lab" target="_blank" rel="noreferrer">Source ↗</a>
        </nav>
        <div className="clouds">
          <p>VALIDATED FOUNDATIONS</p>
          <div><span className="dot aws" />AWS EKS <strong>plan-tested</strong></div>
          <div><span className="dot azure" />Azure AKS <strong>plan-tested</strong></div>
        </div>
        <button className="user" onClick={switchUser} aria-label="Switch seeded demo identity"><div className="avatar">{user.initials}</div><div><b>{user.name}</b><small>{user.role}</small></div><span>↻</span></button>
      </aside>

      <section className="workspace" id="command-center">
        <header><div><p className="eyebrow">VERIFIED ENTERPRISE RELIABILITY LAB</p><h1>Reliability engineering, with receipts.</h1><p className="sub">A runnable workload, governed agents, multi-cloud infrastructure, and measured recovery—built as one reproducible system.</p></div><div className="status"><span />12 / 12 showcase gates passed</div></header>

        <div className="stats" id="evidence">
          <article><p>TEST SUITE</p><strong>200</strong><small>Python behavior tests</small></article>
          <article><p>CLOUD FOUNDATIONS</p><strong>2</strong><small>EKS + AKS validated</small></article>
          <article><p>POD RECOVERY</p><strong>2.443s</strong><small>2/2 ready after deletion</small></article>
          <article><p>HIGH / CRITICAL</p><strong>0</strong><small>repository + image scan</small></article>
        </div>

        <section className="incident">
          <div className="incidentHead"><div><span className={incidentState === "resolved" ? "severity resolved" : "severity"}>{incidentState === "resolved" ? "RESOLVED" : "SEV-2 LAB"}</span><span className="live">● {incidentState.toUpperCase()} · LOCAL ONLY</span><h2>Controlled checkout failure</h2><p>checkout-api · Docker Compose · No production users</p></div><button onClick={() => setReviewing(true)}>Review governed action <span>→</span></button></div>
          <div className="incidentGrid">
            <div className="diagnosis">
              <p className="sectionLabel">AGENT DIAGNOSIS · READ ONLY</p>
              <div className="confidence"><div className="score">99<small>%</small></div><div><b>Controlled fault mode is active</b><p>The user-facing checkout path returned 503 while process health stayed green. The exported fault gauge independently reported <code>errors</code>.</p></div></div>
              <div className="evidence"><span>3 runtime signals</span><span>1 contradicting signal</span><span>Request-bound approval</span></div>
              <div className="action"><div><p>{incidentState === "resolved" ? "ACTION VERIFIED" : "RECOMMENDED ACTION"}</p><b>{incidentState === "resolved" ? "Fault mode none · checkout recovered" : incidentState === "recovering" ? "Recovery in progress…" : "Restore checkout fault mode to none"}</b><small>{incidentState === "resolved" ? "Health 200 and audit chain verified" : `${user.canApprove && user.active ? "Authorized role" : "Approval denied for this identity"} · medium risk · exact target only`}</small></div><button disabled={incidentState !== "active"} onClick={() => setReviewing(true)}>{incidentState === "active" ? "Review action" : incidentState === "recovering" ? "Executing…" : "Verified"}</button></div>
            </div>
            <div className="timeline"><p className="sectionLabel">COMMITTED EVIDENCE TIMELINE</p>{signals.map((signal) => <div className="signal" key={signal.title}><time>{signal.time}</time><span className={`signalDot ${signal.tone}`} /><div><b>{signal.title}</b><small>{signal.source}</small></div></div>)}<a className="linkButton" href="https://github.com/justinmail735-eng/Sai-SRE-AI_lab/blob/codex/enterprise-sre-agents/docs/postmortems/INC-DEMO-ERROR.md" target="_blank" rel="noreferrer">Read the generated postmortem →</a></div>
          </div>
        </section>

        <section className="architecture" id="architecture">
          <div className="architectureIntro"><p className="eyebrow">ONE SYSTEM, FOUR ENGINEERING SURFACES</p><h2>Built beyond the happy path.</h2><p>Every layer has an executable check, a documented trust boundary, and evidence that distinguishes what runs locally from what is validated as cloud infrastructure code.</p></div>
          <div className="capabilityGrid">{capabilities.map((item) => <article key={item.label}><span>{item.label}</span><h3>{item.title}</h3><p>{item.body}</p></article>)}</div>
          <div className="proofBar"><div><strong>OpenTelemetry</strong><small>live pipeline</small></div><div><strong>Argo CD + Helm</strong><small>GitOps desired state</small></div><div><strong>Terraform</strong><small>mocked provider plans</small></div><div><strong>Cosign + Kyverno</strong><small>signature policy</small></div><div><strong>Trivy + Syft</strong><small>scan + SBOM</small></div></div>
          <p className="scopeNote"><b>Truthful scope:</b> the workload, telemetry, failure injection, agents, and Kubernetes recovery run locally. AWS and Azure foundations are provider-schema validated and plan-tested without creating paid resources. Live cloud telemetry adapters remain future work.</p>
        </section>
      </section>

      {reviewing && <div className="modalBackdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="review-title"><button className="close" onClick={() => setReviewing(false)} aria-label="Close">×</button><p className="eyebrow">GOVERNED ACTION REVIEW</p><h2 id="review-title">Recover checkout-api</h2><p className="modalText">This interactive portfolio replay mirrors the tested local action. The real broker binds approval to request <code>ACT-C2E54DAF61EB</code>, checks policy and identity, uses a fixed adapter, verifies recovery, and appends an audit hash.</p><div className="reviewRows"><div><span>Target</span><b>local / checkout-api</b></div><div><span>Risk</span><b>Medium · exact action allowlist</b></div><div><span>Verification</span><b>Fault none · health HTTP 200</b></div><div><span>Identity</span><b>{user.name} · {user.active ? "active" : "disabled"}</b></div></div>{user.canApprove && user.active ? <div className="modalActions"><button className="secondary" onClick={() => setReviewing(false)}>Reject</button><button className="approve" onClick={approveRecovery}>Approve local recovery</button></div> : <div className="permission">Denied: this seeded identity is not active with an authorized approval role.</div>}</section></div>}
    </main>
  );
}
