"use client";

import { useCallback, useEffect, useState } from "react";
import { Band, BandBar, Disclaimer, Notice, Refused, TopBar, formatTime } from "@/components/ui";
import { ApiError, authApi, clearSession, getToken, setSession, staffApi } from "@/lib/api";
import type {
  ActionCatalogue,
  Analytics,
  AuditRow,
  CurrentUser,
  QueueItem,
  RulesResponse,
  StaffCaseDetail,
} from "@/lib/types";

type Tab = "queue" | "analytics" | "audit" | "rules";

export default function StaffConsole() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [pid, setPid] = useState("");
  const [password, setPassword] = useState("");
  const [who, setWho] = useState<CurrentUser | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("queue");
  const [disclaimer, setDisclaimer] = useState<string | undefined>();

  /** The numeric id, because every staff endpoint is keyed on it. */
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<StaffCaseDetail | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [rules, setRules] = useState<RulesResponse | null>(null);
  const [catalogue, setCatalogue] = useState<ActionCatalogue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<{ title: string; body: string } | null>(null);
  const [note, setNote] = useState("");
  const [queue, setQueue] = useState<QueueItem[]>([]);

  useEffect(() => {
    if (getToken()) {
      authApi
        .me()
        .then((m) => {
          setWho(m);
          setToken(getToken());
        })
        .catch(() => clearSession());
    }
    setReady(true);
  }, []);

  const isAdmin = who?.role === "district_admin" || who?.role === "state_admin";
  const canSignOff = who?.role === "district_admin" || who?.role === "state_admin";

  const loadQueue = useCallback(async () => {
    const rows = await staffApi.queue();
    setQueue(rows);
    setSelected((prev) => {
      if (prev !== null && rows.some((r) => r.case_id === prev)) return prev;
      return rows.length ? rows[0].case_id : null;
    });
  }, []);

  const loadDetail = useCallback(async (caseId: number) => {
    setDetail(await staffApi.caseDetail(caseId));
  }, []);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      await loadQueue();
      if (selected) await loadDetail(selected);
      if (isAdmin) {
        setAnalytics(await staffApi.analytics());
        setAudit(await staffApi.audit());
      }
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 401 || e.status === 403) {
          clearSession();
          setWho(null);
          setToken(null);
        }
        setError(typeof e.detail === "string" ? e.detail : e.message);
      } else {
        setError(String(e));
      }
    }
  }, [loadQueue, loadDetail, selected, isAdmin]);

  useEffect(() => {
    if (!token) return;
    void refresh();
    staffApi.catalogue().then(setCatalogue).catch(() => setCatalogue(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setLoginError(null);
    try {
      const r = await authApi.login({ pseudonym_id: pid.trim(), password });
      // sessionStorage only, never localStorage: a token that outlives the tab
      // is a token left behind on a shared machine.
      setSession(r.access_token, r.role);
      setToken(r.access_token);
      setWho(await authApi.me());
      setPassword("");
    } catch (err) {
      setLoginError(err instanceof ApiError ? String(err.detail ?? err.message) : String(err));
    }
  }

  function logout() {
    clearSession();
    setWho(null);
    setToken(null);
    setQueue([]);
    setDetail(null);
  }

  async function act(action: string) {
    if (!selected) return;
    setRefusal(null);
    setError(null);
    try {
      await staffApi.act(selected, { action, note: note.trim() || undefined });
      setNote("");
      await loadDetail(selected);
      await loadQueue();
    } catch (e) {
      if (e instanceof ApiError) {
        const body = typeof e.detail === "string" ? e.detail : e.message;
        // 409 is the closure gate refusing. It is the expected, correct
        // outcome here, so it gets its own surface rather than a red error.
        if (e.status === 409) setRefusal({ title: "The backend refused this action", body });
        else setError(body);
      } else setError(String(e));
    }
  }

  async function closeCase() {
    if (selected === null) return;
    setRefusal(null);
    try {
      await staffApi.close(selected, note.trim() || undefined);
      setNote("");
      await loadDetail(selected);
      await loadQueue();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setRefusal({ title: "Closure refused by the safety gate", body: String(e.detail) });
        await loadDetail(selected);
      } else if (e instanceof ApiError) {
        setError(String(e.detail ?? e.message));
      } else setError(String(e));
    }
  }

  async function openTab(next: Tab) {
    setTab(next);
    try {
      if (next === "analytics") setAnalytics(await staffApi.analytics());
      if (next === "audit") setAudit(await staffApi.audit());
      if (next === "rules") setRules(await staffApi.rules());
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail ?? e.message) : String(e));
    }
  }

  /* ---------------- login ---------------- */

  if (ready && !token) {
    return (
      <>
        <TopBar />
        <main className="page narrow">
          <Disclaimer text={disclaimer} />
          <h1>Staff sign in</h1>
          <p className="muted">
            Access is scoped by role and district on the server. A counsellor
            cannot open another district&rsquo;s queue, and no role can reach
            the police view.
          </p>
          <form className="card" onSubmit={login}>
            <div style={{ marginBottom: 14 }}>
              <label htmlFor="pid">Pseudonym ID</label>
              <input
                id="pid"
                value={pid}
                onChange={(e) => setPid(e.target.value)}
                placeholder="staff.counsellor.1"
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
          </form>
          <div className="card">
            <h2>Demo accounts</h2>
            <p className="hint">
              Password <code className="mono">demo-counsellor-14566</code> for
              all of them. Run <code className="mono">python seed_demo_data.py --reset</code>{" "}
              first.
            </p>
            <div className="row">
              {[
                ["staff.counsellor.1", "counsellor, Bhopal"],
                ["staff.counsellor.2", "counsellor, Indore"],
                ["admin.district.mp", "district admin, Bhopal"],
                ["admin.state.mp", "state admin"],
              ].map(([id, desc]) => (
                <button key={id} onClick={() => setPid(id)} className="ghost" style={{ fontSize: 13 }}>
                  {id} <span className="faint">&middot; {desc}</span>
                </button>
              ))}
            </div>
          </div>
        </main>
      </>
    );
  }

  /* ---------------- console ---------------- */

  const recorded = new Set((detail?.actions ?? []).map((a) => a.action));
  // The gate's requirement list lives on the catalogue, not on the case, so it
  // is identical for every case and always matches what the server enforces.
  const mandatory = catalogue?.mandatory_before_critical_close ?? [];
  const missing = mandatory.filter((a) => !recorded.has(a));
  const label = (action: string) => catalogue?.actions.find((x) => x.action === action)?.label ?? action;
  const allowed = (catalogue?.actions ?? []).filter((a) => a.allowed && (!who || a.allowed_roles.includes(who.role)));

  return (
    <>
      <TopBar
        right={
          <span className="faint">
            {who?.pseudonym_id} &middot; {who?.role}
            {who?.district ? ` \u00b7 ${who.district}` : " \u00b7 all districts"}
          </span>
        }
      />
      <main className="page">
        <Disclaimer text={disclaimer} />

        <div className="toolbar">
          {(["queue", "analytics", "audit", "rules"] as Tab[])
            .filter((t) => (t === "queue" ? true : isAdmin))
            .map((t) => (
              <button
                key={t}
                className={tab === t ? "primary" : "ghost"}
                onClick={() => openTab(t)}
              >
                {t === "queue" ? "Queue" : t === "analytics" ? "Analytics" : t === "audit" ? "Audit trail" : "Engine rules"}
              </button>
            ))}
          <span style={{ flex: 1 }} />
          <button className="ghost" onClick={() => void refresh()}>
            Refresh
          </button>
          <button className="ghost" onClick={logout}>
            Sign out
          </button>
        </div>

        {error && <Notice kind="error">{error}</Notice>}

        {tab === "queue" && (
          <div className="grid2" style={{ gridTemplateColumns: "minmax(300px, 400px) 1fr", alignItems: "start" }}>
            <div className="card" style={{ margin: 0 }}>
              <h2>Queue</h2>
              <p className="hint">
                {who?.district
                  ? `Scoped to ${who.district} by the server.`
                  : "All districts visible to this role."}{" "}
                {queue.length} case(s).
              </p>
              {queue.length === 0 ? (
                <p className="muted">No cases.</p>
              ) : (
                <table className="data">
                  <thead>
                    <tr>
                      <th>Ref</th>
                      <th>Band</th>
                      <th className="num">SVI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {queue.map((item) => (
                      <tr
                        key={item.case_id}
                        className={selected === item.case_id ? "selected" : ""}
                        onClick={() => {
                          setSelected(item.case_id);
                          setRefusal(null);
                          void loadDetail(item.case_id);
                        }}
                        style={{ cursor: "pointer" }}
                      >
                        <td className="mono">{item.case_ref}</td>
                        <td>
                          <Band value={item.category} />
                          {item.is_critical_override && (
                            <div className="faint" title={item.override_reason ?? ""}>
                              override
                            </div>
                          )}
                        </td>
                        <td className="num">{item.composite_score.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div>
              {!detail ? (
                <div className="card">
                  <p className="muted">Select a case.</p>
                </div>
              ) : (
                <>
                  <div className="card">
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <div>
                        <h2 className="mono">{detail.case.ref}</h2>
                        <p className="faint" style={{ margin: 0 }}>
                          {detail.case.district ?? "unspecified district"} &middot; {detail.case.language} &middot;{" "}
                          {detail.case.channel} &middot; opened {formatTime(detail.case.created_at)}
                        </p>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <Band value={detail.category} />
                        <div className="score-big" style={{ marginTop: 6 }}>
                          {detail.composite_score.toFixed(1)}
                        </div>
                      </div>
                    </div>

                    {detail.is_critical_override && (
                      <Notice kind="warn">
                        <strong>Critical Override applied.</strong>{" "}
                        {detail.override_reason}. The composite above would have
                        placed this case lower; a critical-tier indicator moved
                        it up.
                      </Notice>
                    )}

                    <h3>How the number was reached</h3>
                    <div className="weights" title="Component contribution">
                      {Object.entries(detail.svi.weights).map(([k, v]) => (
                        <i key={k} className={k} style={{ width: `${v * 100}%` }} />
                      ))}
                    </div>
                    <p className="faint" style={{ marginTop: 6 }}>
                      weights {JSON.stringify(detail.svi.weights)} &middot;{" "}
                      {detail.method_note}
                    </p>

                    <div className="grid2" style={{ marginTop: 12 }}>
                      <div>
                        <div className="faint">Text</div>
                        <div className="mono">{detail.svi.text_score.toFixed(1)}</div>
                      </div>
                      <div>
                        <div className="faint">Vocal</div>
                        <div className="mono">
                          {detail.svi.weights.vocal === undefined
                            ? "no voice turn"
                            : detail.svi.vocal_score.toFixed(1)}
                        </div>
                      </div>
                      <div>
                        <div className="faint">Behavioural</div>
                        <div className="mono">{detail.svi.behavioral_score.toFixed(1)}</div>
                      </div>
                      <div>
                        <div className="faint">SLA</div>
                        <div className="mono">{detail.sla_state}</div>
                      </div>
                    </div>
                    <p className="faint" style={{ marginTop: 10 }}>
                      {detail.sla_label}
                      {detail.exposes_to_law_enforcement &&
                        " · visible to law enforcement because a human recorded a police liaison"}
                    </p>
                  </div>

                  {/* The closure gate. */}
                  {detail.category === "Critical" && (
                    <div className="gate">
                      <h3>Critical closure gate</h3>
                      <p style={{ margin: 0 }}>
                        This case cannot be closed until a human has done the
                        following, and an administrator has signed it off.
                      </p>
                      <ul>
                        {mandatory.map((a) => (
                          <li key={a} className={missing.includes(a) ? "todo" : "done"}>
                            {missing.includes(a) ? "Not yet: " : "Done: "}
                            {label(a)}
                          </li>
                        ))}
                        <li className={canSignOff ? "todo" : "done"}>
                          {canSignOff
                            ? "Administrator sign-off: pending"
                            : "Administrator sign-off: requires an admin role"}
                        </li>
                      </ul>
                    </div>
                  )}

                  {refusal && (
                    <Refused title={refusal.title}>
                      <p style={{ margin: "0 0 8px" }}>{refusal.body}</p>
                      <p className="faint" style={{ margin: 0 }}>
                        This is the guardrail working. Nothing was changed.
                      </p>
                    </Refused>
                  )}

                  <div className="card">
                    <h2>Record a human action</h2>
                    <p className="hint">
                      Every action is written to the audit trail with the actor
                      and the time. Nothing here is automatic.
                    </p>
                    <label className="sr-only" htmlFor="note">
                      Note
                    </label>
                    <textarea
                      id="note"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="What did you do? (optional)"
                      style={{ minHeight: 70, marginBottom: 12 }}
                    />
                    <div className="row">
                      {allowed.map((a) => (
                        <button key={a.action} onClick={() => act(a.action)}>
                          {a.label}
                        </button>
                      ))}
                    </div>
                    <hr className="sep" />
                    <button className="danger" onClick={closeCase}>
                      Attempt to close this case
                    </button>
                    <p className="faint" style={{ marginTop: 8 }}>
                      Try this on a Critical case: the request is refused and the
                      missing actions are named.
                    </p>
                  </div>

                  <div className="card">
                    <h2>Action ledger</h2>
                    {detail.actions.length === 0 ? (
                      <p className="muted">Nothing recorded yet.</p>
                    ) : (
                      <ul className="ledger">
                        {detail.actions.map((a) => (
                          <li key={a.id}>
                            <span>
                              {label(a.action)}
                              {a.note && <div className="faint">{a.note}</div>}
                            </span>
                            <span className="faint">
                              {a.actor_role} &middot; {formatTime(a.created_at)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <div className="card">
                    <h2>What the person said</h2>
                    {detail.interactions.length === 0 && <p className="muted">No turns.</p>}
                    {detail.interactions.map((turn) => (
                      <div className="turn" key={turn.id}>
                        <div className="faint">
                          {turn.channel} &middot; {formatTime(turn.created_at)} &middot;{" "}
                          {turn.response_latency_ms ? `${turn.response_latency_ms}ms` : ""}{" "}
                          {turn.keypad_presses ? `keys ${turn.keypad_presses}` : ""}
                        </div>
                        {(turn.raw_text || turn.transcribed_text) && (
                          <div className="said">{turn.raw_text || turn.transcribed_text}</div>
                        )}
                        {turn.self_report && Object.keys(turn.self_report).length > 0 && (
                          <div className="faint">
                            self-report {JSON.stringify(turn.self_report)}
                          </div>
                        )}
                        {turn.text_analysis && (
                          <>
                            <div>
                              <span className="faint">text risk </span>
                              <span className="mono">{turn.text_analysis.text_risk_score.toFixed(1)}</span>
                              <span className="faint">
                                {" "}
                                &middot; sentiment {turn.text_analysis.sentiment} (
                                {turn.text_analysis.sentiment_score.toFixed(2)}) &middot; lexicon{" "}
                                {turn.text_analysis.lexicon_version}
                              </span>
                            </div>
                            {turn.text_analysis.risk_flags.length > 0 && (
                              <div style={{ marginTop: 6 }}>
                                {turn.text_analysis.risk_flags.map((f) => (
                                  <span
                                    key={f}
                                    className={`flag${detail.is_critical_override && f === "self_harm_ideation" ? " critical" : ""}`}
                                    title={`lexicon flag raised by ${turn.text_analysis?.method} (${turn.text_analysis?.lexicon_version})`}
                                  >
                                    {f}
                                  </span>
                                ))}
                              </div>
                            )}
                          </>
                        )}
                        {turn.audio_analysis && (
                          <p className="faint" style={{ marginTop: 6 }}>
                            vocal {turn.audio_analysis.vocal_stress_score.toFixed(1)} &middot;{" "}
                            {turn.audio_analysis.method} &middot; {turn.audio_analysis.notes}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {tab === "analytics" && analytics && (
          <div className="card">
            <h2>Analytics &middot; {analytics.scope}</h2>
            <p className="hint">Scoped by the server, not by the browser.</p>
            <div className="grid2">
              {(["Low", "Moderate", "High", "Critical"] as const).map((band) => (
                <BandBar
                  key={band}
                  value={band}
                  counts={analytics.risk_distribution as unknown as Record<string, number>}
                />
              ))}
            </div>
            <hr className="sep" />
            <div className="grid2">
              <div>
                <h3>By channel</h3>
                {Object.entries(analytics.cases_by_channel).map(([k, v]) => (
                  <p key={k} className="mono">
                    {k}: {v}
                  </p>
                ))}
              </div>
              <div>
                <h3>By language</h3>
                {Object.entries(analytics.cases_by_language).map(([k, v]) => (
                  <p key={k} className="mono">
                    {k}: {v}
                  </p>
                ))}
              </div>
            </div>
            <hr className="sep" />
            <h3>Critical overrides by reason</h3>
            {Object.keys(analytics.override_reasons).length === 0 ? (
              <p className="muted">None.</p>
            ) : (
              Object.entries(analytics.override_reasons).map(([k, v]) => (
                <p key={k} className="mono">
                  {k}: {v}
                </p>
              ))
            )}
          </div>
        )}

        {tab === "audit" && (
          <div className="card">
            <h2>Audit trail</h2>
            <p className="hint">
              Every read and every action, attributed and timestamped. The
              audit trail never stores message text.
            </p>
            <table className="data">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Target</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((row) => (
                  <tr key={row.id}>
                    <td className="faint">{formatTime(row.created_at)}</td>
                    <td className="mono">{row.actor_role}</td>
                    <td className="mono">{row.action}</td>
                    <td className="mono">{row.target_id ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "rules" && rules && (
          <div className="card">
            <h2>Engine rules</h2>
            <p className="hint">
              Published so a counsellor can see exactly how the number was
              produced. The engine is deterministic: same input, same output.
            </p>
            <h3>SVI weights</h3>
            <pre className="mono" style={{ background: "var(--wash)", padding: 12, borderRadius: 8, overflow: "auto" }}>
              {JSON.stringify(rules.svi_weights, null, 2)}
            </pre>
            <h3>Bands</h3>
            <pre className="mono" style={{ background: "var(--wash)", padding: 12, borderRadius: 8, overflow: "auto" }}>
              {JSON.stringify(rules.svi_bands, null, 2)}
            </pre>
            <h3>Critical override reasons</h3>
            {Object.entries(rules.override_reasons).map(([k, v]) => (
              <p key={k} style={{ margin: "4px 0" }}>
                <code className="mono">{k}</code> &mdash; {v}
              </p>
            ))}
            <hr className="sep" />
            <h3>Recommendation rules</h3>
            {rules.recommendation_rules.map((rule) => (
              <div key={rule.id} className="turn">
                <div className="mono">{rule.id}</div>
                <div>{rule.note}</div>
                <div className="faint">
                  {rule.when_category ? `band=${rule.when_category} ` : ""}
                  {rule.when_flags_any ? `flags=${rule.when_flags_any.join("|")} ` : ""}
                  &rarr; {rule.actions.join(", ")}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </>
  );
}
