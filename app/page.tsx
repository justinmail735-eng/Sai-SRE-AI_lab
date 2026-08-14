"use client";

import { useState } from "react";

const signals = [
  { time: "14:32", title: "checkout-api error rate crossed 5%", source: "AWS CloudWatch", tone: "critical" },
  { time: "14:29", title: "Deployment checkout-api:v2.14.0 completed", source: "AWS CodeDeploy", tone: "change" },
  { time: "14:26", title: "payment-worker latency remains healthy", source: "Azure Monitor", tone: "healthy" },
];

const users = [
  { name: "Avery Morgan", initials: "AM", role: "On-call engineer", canApprove: true },
  { name: "Jordan Lee", initials: "JL", role: "SRE lead", canApprove: true },
  { name: "Riley Chen", initials: "RC", role: "Engineering manager", canApprove: false },
];

export default function Home() {
  const [userIndex, setUserIndex] = useState(0);
  const [reviewing, setReviewing] = useState(false);
  const [incidentState, setIncidentState] = useState<"active" | "rolling-back" | "resolved">("active");
  const user = users[userIndex];

  function switchUser() {
    setUserIndex((userIndex + 1) % users.length);
  }

  function approveRollback() {
    setIncidentState("rolling-back");
    setReviewing(false);
    window.setTimeout(() => setIncidentState("resolved"), 2200);
  }

  return (
    <main className="shell">
      <aside className="rail">
        <div className="brand"><span className="brandMark">S</span><span>SAI / OPS</span></div>
        <nav>
          <a className="active" href="#">Command center</a>
          <a href="#">Incidents <span className="badge">1</span></a>
          <a href="#">Services</a>
          <a href="#">Runbooks</a>
          <a href="#">Postmortems</a>
        </nav>
        <div className="clouds">
          <p>CONNECTED CLOUDS</p>
          <div><span className="dot aws" />AWS <strong>8 services</strong></div>
          <div><span className="dot azure" />Azure <strong>5 services</strong></div>
        </div>
        <button className="user" onClick={switchUser} aria-label="Switch demo user"><div className="avatar">{user.initials}</div><div><b>{user.name}</b><small>{user.role}</small></div><span>↻</span></button>
      </aside>

      <section className="workspace">
        <header><div><p className="eyebrow">COMMAND CENTER · DEMO WORKSPACE</p><h1>Good afternoon, {user.name.split(" ")[0]}.</h1><p className="sub">{incidentState === "resolved" ? "The incident is resolved. Recovery evidence is ready for review." : "One incident needs your attention. The system has already gathered the evidence."}</p></div><div className="status"><span />All systems connected</div></header>

        <div className="stats">
          <article><p>OPEN INCIDENTS</p><strong className={incidentState === "resolved" ? "" : "red"}>{incidentState === "resolved" ? "0" : "1"}</strong><small>{incidentState === "resolved" ? "All clear" : "1 critical"}</small></article>
          <article><p>SERVICES</p><strong>13</strong><small>{incidentState === "resolved" ? "13 healthy" : "12 healthy"}</small></article>
          <article><p>SLO COMPLIANCE</p><strong>{incidentState === "resolved" ? "99.1%" : "92.3%"}</strong><small className={incidentState === "resolved" ? "" : "down"}>{incidentState === "resolved" ? "↑ recovering" : "↓ 3.1% this hour"}</small></article>
          <article><p>ERROR BUDGET</p><strong>71%</strong><small>30-day window</small></article>
        </div>

        <section className="incident">
          <div className="incidentHead"><div><span className={incidentState === "resolved" ? "severity resolved" : "severity"}>{incidentState === "resolved" ? "RESOLVED" : "SEV-1"}</span><span className="live">● {incidentState.replace("-", " ").toUpperCase()} · 12 MIN</span><h2>Checkout failures after production deployment</h2><p>checkout-api · us-east-1 · Production</p></div><button onClick={() => setReviewing(true)}>Open incident room <span>→</span></button></div>
          <div className="incidentGrid">
            <div className="diagnosis">
              <p className="sectionLabel">AGENT DIAGNOSIS</p>
              <div className="confidence"><div className="score">87<small>%</small></div><div><b>Likely deployment regression</b><p>The error spike began three minutes after <code>v2.14.0</code> deployed. Failures are isolated to the new version; dependencies remain healthy.</p></div></div>
              <div className="evidence"><span>3 supporting signals</span><span>1 contradicting signal</span><span>High confidence</span></div>
              <div className="action"><div><p>{incidentState === "resolved" ? "ACTION COMPLETED" : "RECOMMENDED ACTION"}</p><b>{incidentState === "resolved" ? "Rollback verified — service recovered" : incidentState === "rolling-back" ? "Rollback in progress…" : "Roll back checkout-api to v2.13.2"}</b><small>{incidentState === "resolved" ? "Error rate returned below the SLO threshold" : `${user.canApprove ? "Requires your approval" : "Approval restricted to on-call or SRE lead"} · Estimated recovery: 4 min`}</small></div><button disabled={incidentState !== "active"} onClick={() => setReviewing(true)}>{incidentState === "active" ? "Review action" : incidentState === "rolling-back" ? "Executing…" : "View evidence"}</button></div>
            </div>
            <div className="timeline"><p className="sectionLabel">EVIDENCE TIMELINE</p>{signals.map((signal) => <div className="signal" key={signal.time}><time>{signal.time}</time><span className={`signalDot ${signal.tone}`} /><div><b>{signal.title}</b><small>{signal.source}</small></div></div>)}<button className="linkButton">View all 9 events →</button></div>
          </div>
        </section>
      </section>
      {reviewing && <div className="modalBackdrop" role="presentation" onMouseDown={() => setReviewing(false)}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="review-title" onMouseDown={(event) => event.stopPropagation()}><button className="close" onClick={() => setReviewing(false)} aria-label="Close">×</button><p className="eyebrow">RUNBOOK ACTION REVIEW</p><h2 id="review-title">Rollback checkout-api</h2><p className="modalText">The agent proposes restoring version <code>v2.13.2</code>. This action changes production and is never executed without an authorized human.</p><div className="reviewRows"><div><span>Evidence</span><b>3 supporting · 1 contradicting</b></div><div><span>Risk</span><b>Medium · customer traffic affected</b></div><div><span>Verification</span><b>5xx below 1% for five minutes</b></div><div><span>Signed in as</span><b>{user.name} · {user.role}</b></div></div>{user.canApprove ? <div className="modalActions"><button className="secondary" onClick={() => setReviewing(false)}>Reject</button><button className="approve" onClick={approveRollback}>Approve rollback</button></div> : <div className="permission">Read-only role: ask the on-call engineer or SRE lead to approve this action.</div>}</section></div>}
    </main>
  );
}
