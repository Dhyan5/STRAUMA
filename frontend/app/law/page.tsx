"use client";

import { useCallback, useEffect, useState } from "react";
import { Band, Disclaimer, Notice, TopBar, formatTime } from "@/components/ui";
import { ApiError, authApi, clearSession, getToken, lawApi, setSession } from "@/lib/api";
import type { LawCase, LawPolicy } from "@/lib/types";

/**
 * The most restricted surface in the system.
 *
 * Three things are true here by construction, and the copy says so out loud:
 *  1. The list only ever contains cases a human explicitly referred.
 *  2. There is no transcript, no identity and no score. `LawCase` has no such
 *     field, and the backend builds the projection server-side.
 *  3. Opening this page writes an audit row, because who looked is as
 *     important as what was shared.
 */
export default function LawEnforcement() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [pid, setPid] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [cases, setCases] = useState<LawCase[]>([]);
  const [policy, setPolicy] = useState<LawPolicy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [disclaimer, setDisclaimer] = useState<string | undefined>();

  const load = useCallback(async () => {
    setError(null);
    try {
      setCases(await lawApi.cases());
      setPolicy(await lawApi.policy());
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
        clearSession();
        setToken(null);
        setError("Your session is not valid for this view.");
        return;
      }
      setError(e instanceof ApiError ? String(e.detail ?? e.message) : String(e));
    }
  }, []);

  useEffect(() => {
    if (getToken()) {
      authApi
        .me()
        .then((m) => {
          if (m.role === "law_enforcement") setToken(getToken());
          else clearSession();
        })
        .catch(() => clearSession());
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (token) void load();
  }, [token, load]);

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setLoginError(null);
    try {
      const r = await authApi.login({ pseudonym_id: pid.trim(), password });
      if (r.role !== "law_enforcement") {
        setLoginError(
          "That account is not a law-enforcement account. The police view is not available to counsellors or administrators, by design.",
        );
        return;
      }
      setSession(r.access_token, r.role);
      setToken(r.access_token);
    } catch (err) {
      setLoginError(err instanceof ApiError ? String(err.detail ?? err.message) : String(err));
    }
  }

  if (ready && !token) {
    return (
      <>
        <TopBar />
        <main className="page narrow">
          <Disclaimer text={disclaimer} />
          <h1>District nodal officer sign in</h1>
          <Notice kind="warn">
            This view contains only cases a counsellor or administrator has
            <strong> explicitly referred</strong>. A Critical band on its own
            does not put a case here. Every sign-in and every list read is
            written to the audit trail.
          </Notice>
          <form className="card" onSubmit={login}>
            <div style={{ marginBottom: 14 }}>
              <label htmlFor="pid">Pseudonym ID</label>
              <input
                id="pid"
                value={pid}
                onChange={(e) => setPid(e.target.value)}
                placeholder="police.liaison.mp"
                autoComplete="username"
              />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label htmlFor="pw">Password</label>
              <input
                id="pw"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            {loginError && <Notice kind="error">{loginError}</Notice>}
            <button className="primary" type="submit" disabled={!pid.trim() || !password}>
              Sign in
            </button>
            <p className="faint" style={{ marginTop: 12 }}>
              Demo: <code className="mono">police.liaison.mp</code> /{" "}
              <code className="mono">demo-counsellor-14566</code>
            </p>
          </form>
        </main>
      </>
    );
  }

  return (
    <>
      <TopBar
        right={
          <button
            className="ghost"
            onClick={() => {
              clearSession();
              setToken(null);
            }}
          >
            Sign out
          </button>
        }
      />
      <main className="page">
        <Disclaimer text={disclaimer} />
        {error && <Notice kind="error">{error}</Notice>}

        <div className="card">
          <h2>Referred cases</h2>
          <p className="hint">
            {cases.length} case(s) referred. This list is built server-side. No
            transcript, no name, and no score is available here even to an
            authenticated officer.
          </p>

          {cases.length === 0 ? (
            <p className="muted">
              Nothing has been referred. A case appears here only after a human
              records a police-liaison action.
            </p>
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>Case ref</th>
                  <th>District</th>
                  <th>Band</th>
                  <th>Reason for referral</th>
                  <th>Action required</th>
                  <th>Referred by</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => (
                  <tr key={c.case_ref}>
                    <td className="mono">{c.case_ref}</td>
                    <td>{c.district ?? "unspecified"}</td>
                    <td>
                      <Band value={c.category} />
                    </td>
                    <td>
                      {c.override_reason}
                      <div className="faint" style={{ marginTop: 4 }}>
                        {c.immediate_action_required}
                      </div>
                    </td>
                    <td>
                      {c.category === "Critical" ? (
                        <span className="pill warn">Immediate</span>
                      ) : (
                        <span className="pill">Assessment</span>
                      )}
                    </td>
                    <td className="faint">
                      {c.recorded_by_role}
                      <br />
                      via {c.contact_via}
                    </td>
                    <td className="faint">{formatTime(c.recorded_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <h2>What you can and cannot do here</h2>
          <p className="hint">
            Served by <code className="mono">/api/law-enforcement/policy</code>,
            so the rules below are the server&rsquo;s rules, not this page&rsquo;s.
          </p>
          <ul style={{ lineHeight: 1.75 }}>
            <li>{policy?.visibility_rule ?? "Visibility requires an explicit human referral."}</li>
            <li>Contact the person only through the district nodal officer pathway below.</li>
            <li>
              <strong>Not available:</strong>{" "}
              {(policy?.excluded_fields ?? ["the complainant's words", "identity", "SVI number", "component breakdown"])
                .join(", ")}
              . None of these are sent to this endpoint.
            </li>
            <li>{policy?.audit_note ?? "Every read from this view is audited."}</li>
          </ul>
          <p className="faint">
            Contact via {cases[0]?.contact_via ?? "the district nodal officer"}.
            Tele MANAS 14416 &middot; Women Helpline 181 &middot; NHAA 14566
          </p>
        </div>
      </main>
    </>
  );
}
