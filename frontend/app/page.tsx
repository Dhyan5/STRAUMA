"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Disclaimer, Notice, TopBar, formatTime } from "@/components/ui";
import { publicApi } from "@/lib/api";
import type { EngineStatus } from "@/lib/types";

export default function Home() {
  const [config, setConfig] = useState<{ disclaimer: string; sla_hours: Record<string, number> } | null>(null);
  const [engines, setEngines] = useState<EngineStatus | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    publicApi
      .config()
      .then(setConfig)
      .catch((e) => setProblem(e instanceof Error ? e.message : String(e)));
    publicApi.engines().then(setEngines).catch(() => setEngines(null));
  }, []);

  return (
    <>
      <TopBar />
      <main className="page">
        <Disclaimer text={config?.disclaimer} />
        {problem && (
          <Notice kind="warn">
            <strong>The backend is not reachable.</strong> Start it with{" "}
            <code className="mono">uvicorn main:app --reload</code> in{" "}
            <code className="mono">backend/</code>, then reload. {problem}
          </Notice>
        )}

        <h1>Stress &amp; Trauma Assessment Module</h1>
        <p className="muted" style={{ maxWidth: 720 }}>
          A routing prototype for the National Helpline for Acid Attack Victims
          and People Affected by Acid Attacks. A person reports what is
          happening in their own words and in their language, over chat, voice
          or a phone menu. A transparent, deterministic engine sorts the
          request. <strong>A trained counsellor makes every decision.</strong>
        </p>

        <div className="grid-landing" style={{ margin: "28px 0" }}>
          <Link className="portal-card" href="/victim">
            <span className="tag">For the person seeking help</span>
            <h3>Victim portal</h3>
            <p>
              Tell us what is happening, in your own words and your language.
              No name, no account, no score. You can stop at any time.
            </p>
          </Link>
          <Link className="portal-card" href="/staff">
            <span className="tag">For counsellors and administrators</span>
            <h3>Staff console</h3>
            <p>
              District-scoped queue, full scoring breakdown, the action ledger,
              and the closure gate that refuses to let a Critical case close
              before a human has acted.
            </p>
          </Link>
          <Link className="portal-card" href="/law">
            <span className="tag">For the district nodal officer</span>
            <h3>Law enforcement view</h3>
            <p>
              Only cases a human has explicitly referred. No transcripts, no
              identity, no scores. Every read is written to the audit trail.
            </p>
          </Link>
        </div>

        <div className="card">
          <h2>How a request is handled</h2>
          <ol style={{ lineHeight: 1.75, marginBottom: 0 }}>
            <li>
              The person gives consent and is told, in plain words, that a
              computer will look for signs of urgent need and that every
              decision is made by a person.
            </li>
            <li>
              Text, vocal and behavioural signals are combined into a{" "}
              <strong>Severity Vulnerability Index</strong> on a fixed
              0&ndash;100 scale, using published weights.
            </li>
            <li>
              A small number of <strong>critical-tier indicators</strong> force
              the top band regardless of the number, so a numeric blend cannot
              talk the system down.
            </li>
            <li>
              The case enters a district-scoped queue. A Critical case cannot
              be closed until a counsellor has confirmed direct contact and
              arranged an emergency bridge, and an administrator has signed it
              off.
            </li>
            <li>
              Nothing is shared with any third party unless a human records the
              decision to do so.
            </li>
          </ol>
        </div>

        {config?.sla_hours && (
          <div className="card">
            <h2>Response commitments by band</h2>
            <p className="hint">
              Shown to staff, and shown to the person only as &ldquo;a
              counsellor will contact you&rdquo;. Never shown as a score.
            </p>
            <div className="row">
              {Object.entries(config.sla_hours).map(([band, hours]) => (
                <span key={band} className="pill">
                  {band}: {hours}h
                </span>
              ))}
            </div>
          </div>
        )}

        {engines && (
          <div className="card">
            <h2>What is actually running</h2>
            <p className="hint">
              The prototype reports its own methods rather than claiming more
              than it does.
            </p>
            <table className="data">
              <thead>
                <tr>
                  <th>Component</th>
                  <th>Method</th>
                  <th>Stated limitation</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Text risk</td>
                  <td>
                    Human-curated lexicon, per language, version-tagged
                  </td>
                  <td>
                    Requires professional sign-off. Machine translation is
                    never applied to risk lexicons.
                  </td>
                </tr>
                <tr>
                  <td>Vocal</td>
                  <td className="mono">{engines.audio.method_label}</td>
                  <td>{engines.audio.note}</td>
                </tr>
                <tr>
                  <td>Sentiment</td>
                  <td className="mono">{engines.sentiment.method_label}</td>
                  <td>{engines.sentiment.coverage_caveat}</td>
                </tr>
              </tbody>
            </table>
            <p className="faint" style={{ marginTop: 12, marginBottom: 0 }}>
              Checked {formatTime(new Date().toISOString())} from the running
              backend.
            </p>
          </div>
        )}

        <div className="card">
          <h2>Demo staff logins</h2>
          <p className="hint">
            Password for all demo accounts:{" "}
            <code className="mono">demo-counsellor-14566</code>. These are
            fabricated accounts created by <code className="mono">seed_demo_data.py</code>.
          </p>
          <table className="data">
            <thead>
              <tr>
                <th>Pseudonym ID</th>
                <th>Role</th>
                <th>District</th>
                <th>Shows</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="mono">staff.counsellor.1</td>
                <td>counsellor</td>
                <td>Bhopal</td>
                <td>Bhopal cases only</td>
              </tr>
              <tr>
                <td className="mono">staff.counsellor.2</td>
                <td>counsellor</td>
                <td>Indore</td>
                <td>Indore cases only</td>
              </tr>
              <tr>
                <td className="mono">admin.district.mp</td>
                <td>district_admin</td>
                <td>Bhopal</td>
                <td>Bhopal analytics and audit</td>
              </tr>
              <tr>
                <td className="mono">admin.state.mp</td>
                <td>state_admin</td>
                <td>all</td>
                <td>State-wide analytics, audit, engine rules</td>
              </tr>
              <tr>
                <td className="mono">police.liaison.mp</td>
                <td>law_enforcement</td>
                <td>all</td>
                <td>Referred cases only, minimal projection</td>
              </tr>
            </tbody>
          </table>
        </div>
      </main>
    </>
  );
}
