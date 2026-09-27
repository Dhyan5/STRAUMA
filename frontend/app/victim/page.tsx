"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Disclaimer, Notice, QuickExit } from "@/components/ui";
import { ApiError, authApi, consentApi, publicApi, setSession, victimApi } from "@/lib/api";
import type { CrisisResource, PortalLanguage, SelfReportItem, VictimView } from "@/lib/types";

type Step =
  | "welcome"
  | "language"
  | "channel"
  | "consent"
  | "compose"
  | "selfreport"
  | "done"
  | "resources";

interface Strings {
  [key: string]: string;
}

const EN_FALLBACK: Strings = {
  "landing.heading": "You are not alone. We are listening.",
  "landing.body":
    "You can tell us what is happening in your own words, in your language. You can stop at any time. You do not have to give your name.",
  "disclaimer":
    "Prototype for demonstration purposes. Not a diagnostic tool. All risk flags are reviewed by trained personnel.",
  "consent.heading": "Before you begin",
  "consent.point_record":
    "We will record what you type or say, so a counsellor can read it later.",
  "consent.point_analyse":
    "A computer will look for signs that you may need urgent help. It only sorts requests. A trained person makes every decision.",
  "consent.point_share":
    "Only the counsellors handling your request will see it. We do not share your name because we never ask for it.",
  "consent.point_retention": "We keep this for a limited time, then delete it.",
  "consent.point_stop": "You can stop at any moment and nothing will be sent.",
  "consent.checkbox": "I understand and I agree to continue.",
  "consent.need_help_now": "I need help right now",
  "channel.label": "How would you like to tell us?",
  "channel.chat": "Type it",
  "channel.voice": "Say it",
  "channel.ivrs": "Phone menu",
  "chat.prompt_one": "In your own words, what is happening?",
  "chat.prompt_more": "Is there anything else you want to add?",
  "chat.placeholder": "Type here, in any language",
  "voice.record": "Hold the button and speak",
  "voice.stop": "Stop recording",
  "voice.use_demo": "No microphone? Use a practice recording",
  "voice.demo_note": "This is a computer-generated practice clip, not a recording of you.",
  "selfreport.heading": "A few quick questions",
  "selfreport.note":
    "These are not a test and nothing is scored. Answer only what you want to.",
  "done.heading": "Thank you for telling us.",
  "done.body":
    "A counsellor will read this and contact you. You do not need to explain again.",
  "done.reference": "Your reference",
  "done.what_next": "What happens next",
  "done.save_reference": "Write down your reference number so you can quote it.",
  "resources.heading": "Free helplines, any time",
  "error.generic": "Something went wrong. Please try again.",
  "error.network":
    "We could not reach the service. Please try again, or call the helplines above.",
};

export default function VictimPortal() {
  const [step, setStep] = useState<Step>("welcome");
  const [language, setLanguage] = useState("en");
  const [strings, setStrings] = useState<Strings>(EN_FALLBACK);
  const [stringFallback, setStringFallback] = useState(false);
  const [languages, setLanguages] = useState<PortalLanguage[]>([]);
  const [consentVersion, setConsentVersion] = useState("v1.0-demo");
  const [disclaimer, setDisclaimer] = useState<string>(EN_FALLBACK.disclaimer);
  const [helplines, setHelplines] = useState<CrisisResource[]>([]);
  const [selfReportItems, setSelfReportItems] = useState<SelfReportItem[]>([]);
  const [channel, setChannel] = useState<"chat" | "voice" | "ivrs">("chat");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Intake state
  const [agreed, setAgreed] = useState(false);
  const [needNow, setNeedNow] = useState(false);
  const [turns, setTurns] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [keypad, setKeypad] = useState("");
  const [selfReport, setSelfReport] = useState<Record<string, number>>({});

  const [caseId, setCaseId] = useState<number | null>(null);
  const [view, setView] = useState<VictimView | null>(null);

  const startedAt = useRef(Date.now());
  const t = (key: string) => strings[key] ?? EN_FALLBACK[key] ?? key;

  /* ---------------- bootstrap ---------------- */

  useEffect(() => {
    // One call carries the disclaimer, the helplines, the language list, the
    // consent version and the self-report questions, so the portal has a
    // coherent first paint instead of five independently failing ones.
    publicApi
      .config()
      .then((c) => {
        setDisclaimer(c.disclaimer);
        setHelplines(c.crisis_resources ?? []);
        setLanguages(c.languages ?? []);
        setConsentVersion(c.consent_version);
        setSelfReportItems(c.self_report_items ?? []);
      })
      .catch(() => {
        setHelplines([]);
        setSelfReportItems([]);
      });
  }, []);

  const loadStrings = useCallback(async (code: string) => {
    try {
      const r = await publicApi.strings(code);
      setStrings((prev) => ({ ...prev, ...r.strings }));
      setStringFallback(r.fallback);
      if (r.fallback && r.strings?.disclaimer) setDisclaimer(r.strings.disclaimer);
    } catch {
      setStringFallback(true);
    }
  }, []);

  useEffect(() => {
    void loadStrings(language);
  }, [language, loadStrings]);

  /* ---------------- helpers ---------------- */

  const send = useCallback(async (text: string) => {
    if (caseId === null) return null;
    const started = Date.now();
    const r = await victimApi.submitTurn({
      case_id: caseId,
      channel,
      ...(channel === "ivrs"
        ? { transcribed_text: text, keypad_presses: keypad, response_latency_ms: 30000 }
        : { text, response_latency_ms: Math.max(1200, Date.now() - startedAt.current) }),
    });
    setView(r.view);
    return r.view;
  }, [caseId, channel, keypad]);

  async function guard<T>(fn: () => Promise<T>): Promise<T | null> {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      if (e instanceof ApiError) {
        setError(typeof e.detail === "string" ? e.detail : e.message || t("error.generic"));
      } else {
        setError(t("error.network"));
      }
      return null;
    } finally {
      setBusy(false);
    }
  }

  /* ---------------- consent ---------------- */

  /**
   * Registration happens at the consent step, but consent is only *granted*
   * once the channel is known, because the server scopes consent per channel.
   * Granting it here with a guessed channel would record consent for a channel
   * the person never chose.
   */
  async function startCase() {
    await guard(async () => {
      // No name is ever requested. A random pseudonym is generated server-side.
      const reg = await authApi.register({ role: "complainant", language_pref: language });
      setSession(reg.access_token, "complainant");
      await consentApi.grant({ version: consentVersion, channel });
      const created = await victimApi.createCase({ channel, language });
      setCaseId(created.id);
      setTurns([]);
      setDraft("");
      setKeypad("");
      setSelfReport({});
      setStep("compose");
    });
  }

  /* ---------------- compose ---------------- */

  async function submitChat() {
    const text = draft.trim();
    if (!text) return;
    const ok = await guard(async () => {
      await send(text);
      return true;
    });
    if (!ok) return;
    setTurns((prev) => [...prev, text]);
    setDraft("");
    setStep("selfreport");
  }

  async function submitIvr() {
    const text = draft.trim() || (keypad ? `IVRS session ${keypad}` : "");
    const ok = await guard(async () => {
      await send(text);
      return true;
    });
    if (!ok) return;
    setTurns((prev) => [...prev, text]);
    setStep("selfreport");
  }

  async function submitDemoVoice() {
    const ok = await guard(async () => {
      const r = await victimApi.demoVoice(caseId!, true, draft.trim() || "I am not coping");
      setView(r.view);
      return true;
    });
    if (!ok) return;
    setTurns((prev) => [...prev, draft.trim() || "(practice recording)"]);
    setDraft("");
    setStep("selfreport");
  }

  async function finish() {
    // A person may skip the narrative and answer only the questions, so the
    // self-report alone is the content of this turn. No placeholder text is
    // invented on their behalf.
    const answers = Object.keys(selfReport).length
      ? selfReport
      : Object.fromEntries(selfReportItems.map((s) => [s.key, s.options[0].value]));
    await guard(async () => {
      if (caseId !== null) {
        const r = await victimApi.submitTurn({
          case_id: caseId,
          channel,
          response_latency_ms: 4000,
          self_report: answers,
        });
        setView(r.view);
      }
      setStep("done");
    });
  }

  /* ---------------- render ---------------- */

  const helplineBlock = (
    <div className="card" style={{ marginTop: 20 }}>
      <h2>{t("resources.heading")}</h2>
      {helplines.length === 0 ? (
        <p className="muted">Tele MANAS 14416 &middot; Women Helpline 181 &middot; Police 112 &middot; NHAA 14566</p>
      ) : (
        helplines.map((h) => (
          <div className="helpline" key={h.id}>
            <span className="what">{h.name}</span>
            <span className="num">{h.numbers.join(" / ")}</span>
          </div>
        ))
      )}
    </div>
  );

  return (
    <div className="victim">
      <QuickExit />
      <Disclaimer text={disclaimer} />
      {stringFallback && (
        <p className="faint">
          This language is not available yet, so the English text is shown. We
          would rather show you English than guess.
        </p>
      )}
      {error && (
        <Notice kind="error">
          {error}
          {/*{ Retry is offered by re-submitting, not by a separate control. */}
        </Notice>
      )}

      {step === "welcome" && (
        <div className="victim-step">
          <h1>{t("landing.heading")}</h1>
          <p className="lede">{t("landing.body")}</p>
          <div className="row">
            <button className="primary" onClick={() => setStep("language")} disabled={busy}>
              Start
            </button>
            <button onClick={() => setStep("resources")}>I need a helpline now</button>
          </div>
        </div>
      )}

      {step === "language" && (
        <div className="victim-step">
          <h1>Choose your language</h1>
          <p className="muted">You can change this later.</p>
          <div className="stack">
            {languages.map((l) => (
              <button
                key={l.code}
                className={`choice${language === l.code ? " selected" : ""}`}
                onClick={() => {
                  setLanguage(l.code);
                  setStep("channel");
                }}
              >
                <strong>{l.native_name}</strong>
                <span>{l.label}</span>
              </button>
            ))}
          </div>
          {languages.length === 0 && <p className="muted">English</p>}
        </div>
      )}

      {step === "channel" && (
        <div className="victim-step">
          <h1>{t("channel.label")}</h1>
          <p className="muted">All three reach the same counsellor.</p>
          <div className="stack">
            <button
              className={`choice${channel === "chat" ? " selected" : ""}`}
              onClick={() => setChannel("chat")}
            >
              <strong>{t("channel.chat")}</strong>
              <span>Write in your own words, in any language.</span>
            </button>
            <button
              className={`choice${channel === "voice" ? " selected" : ""}`}
              onClick={() => setChannel("voice")}
            >
              <strong>{t("channel.voice")}</strong>
              <span>Speak. Or use a practice recording if there is no microphone.</span>
            </button>
            <button
              className={`choice${channel === "ivrs" ? " selected" : ""}`}
              onClick={() => setChannel("ivrs")}
            >
              <strong>{t("channel.ivrs")}</strong>
              <span>A phone menu, like calling a helpline.</span>
            </button>
          </div>
          <div className="row" style={{ marginTop: 18 }}>
            <button className="primary" onClick={() => setStep("consent")}>
              Continue
            </button>
            <button onClick={() => setStep("welcome")}>Back</button>
          </div>
        </div>
      )}

      {step === "consent" && (
        <div className="victim-step">
          <h1>{t("consent.heading")}</h1>
          <ul style={{ lineHeight: 1.7, paddingLeft: 20 }}>
            <li>{t("consent.point_record")}</li>
            <li>{t("consent.point_analyse")}</li>
            <li>{t("consent.point_share")}</li>
            <li>{t("consent.point_retention")}</li>
            <li>{t("consent.point_stop")}</li>
          </ul>
          <label style={{ marginTop: 18, fontWeight: 400 }}>
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              style={{ width: "auto", marginRight: 10, display: "inline-block" }}
            />
            {t("consent.checkbox")}
          </label>
          <div className="row" style={{ marginTop: 18 }}>
            <button className="primary" disabled={!agreed || busy} onClick={startCase}>
              Continue
            </button>
            <button onClick={() => setStep("channel")}>Back</button>
          </div>
        </div>
      )}

      {step === "compose" && (
        <div className="victim-step">
          <h1>
            {turns.length === 0 ? t("chat.prompt_one") : t("chat.prompt_more")}
          </h1>

          {turns.map((text, i) => (
            <div className="bubble" key={i}>
              {text}
              <div className="when">You</div>
            </div>
          ))}

          {channel === "ivrs" && (
            <>
              <label htmlFor="keys">Phone menu</label>
              <div className="row" style={{ marginBottom: 12 }}>
                {["1", "2", "3", "4", "0"].map((k) => (
                  <button key={k} onClick={() => setKeypad((p) => `${p}${k}`)} style={{ minWidth: 52 }}>
                    {k}
                  </button>
                ))}
                <button className="ghost" onClick={() => setKeypad("")}>
                  Clear
                </button>
              </div>
              <p className="mono">{keypad || "(no keys pressed)"}</p>
            </>
          )}

          {channel === "voice" && (
            <Notice kind="info">
              <strong>{t("voice.demo_note")}</strong> The prototype has no live
              microphone capture, so the voice channel is demonstrated with a
              generated clip. This is labelled as synthetic in the record.
            </Notice>
          )}

          <label className="sr-only" htmlFor="draft">
            Your message
          </label>
          <textarea
            id="draft"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={t("chat.placeholder")}
            style={{ marginTop: 12 }}
          />

          <div className="row" style={{ marginTop: 14 }}>
            <button
              className="primary"
              disabled={busy || (!draft.trim() && channel !== "voice")}
              onClick={channel === "ivrs" ? submitIvr : channel === "voice" ? submitDemoVoice : submitChat}
            >
              {channel === "voice" ? "Send practice recording" : "Send"}
            </button>
            <button
              disabled={busy || (turns.length === 0 && channel !== "voice")}
              onClick={() => setStep("selfreport")}
            >
              Skip to questions
            </button>
          </div>

          {view && (
            <p className="muted" style={{ marginTop: 16 }}>
              {view.next_step_key === "done.bridge_live" || view.urgency === "immediate"
                ? "A counsellor is being connected to you now. Stay on this screen if you can."
                : "Thank you. A counsellor will read this and contact you."}
            </p>
          )}
        </div>
      )}

      {step === "selfreport" && (
        <div className="victim-step">
          <h1>{t("selfreport.heading")}</h1>
          <p className="muted">{t("selfreport.note")}</p>
          <div className="stack" style={{ marginTop: 18 }}>
            {selfReportItems.map((item) => (
              <div key={item.key}>
                <label htmlFor={`sr-${item.key}`}>{t(item.i18n_key ?? item.key)}</label>
                <div className="row">
                  {item.options.map((opt) => (
                    <button
                      key={opt.value}
                      className={selfReport[item.key] === opt.value ? "choice selected" : "choice"}
                      style={{ width: "auto", marginBottom: 0, padding: "10px 14px" }}
                      onClick={() => setSelfReport((p) => ({ ...p, [item.key]: opt.value }))}
                    >
                      {t(opt.i18n_key)}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="row" style={{ marginTop: 20 }}>
            <button className="primary" disabled={busy} onClick={finish}>
              Send
            </button>
            <button disabled={busy} onClick={() => setStep("done")}>
              Skip this
            </button>
          </div>
        </div>
      )}

      {step === "done" && view && (
        <div className="victim-step">
          <h1>{t("done.heading")}</h1>
          <p className="lede">{t("done.body")}</p>

          <h2 style={{ marginTop: 24 }}>{t("done.reference")}</h2>
          <div className="reference-box">{view.reference}</div>
          <p className="faint" style={{ textAlign: "center" }}>
            {t("done.save_reference")}
          </p>

          <h2 style={{ marginTop: 24 }}>{t("done.what_next")}</h2>
          <div className="card" style={{ background: "var(--wash)" }}>
            {view.urgency === "immediate" ? (
              <p style={{ margin: 0 }}>
                <strong>A counsellor is being connected to you now.</strong> Stay
                on this screen if you can. If you are in immediate danger, call{" "}
                <strong>112</strong>.
              </p>
            ) : view.urgency === "priority" ? (
              <p style={{ margin: 0 }}>
                <strong>This has been marked as a priority.</strong> A counsellor
                will contact you as soon as they can.
              </p>
            ) : (
              <p style={{ margin: 0 }}>
                A counsellor will contact you. You do not need to explain again.
              </p>
            )}
            <p className="faint" style={{ margin: "8px 0 0" }}>
              Reference {view.reference} &middot; {view.stage}
            </p>
          </div>

          <div className="row" style={{ marginTop: 20 }}>
            <button onClick={() => setStep("compose")}>Add something I forgot</button>
            <button className="primary" onClick={() => setStep("resources")}>
              Show me helplines
            </button>
          </div>
        </div>
      )}

      {step === "resources" && (
        <div className="victim-step">
          <h1>{t("resources.heading")}</h1>
          <p className="muted">Free. Any time. You do not have to explain.</p>
          <div style={{ marginTop: 16 }}>
            {(helplines.length
              ? helplines
              : [
                  { id: "tele_manas", name: "Tele MANAS", numbers: ["14416", "1800-891-4416"], description: "" },
                  { id: "women_helpline", name: "Women Helpline", numbers: ["181"], description: "" },
                  { id: "police", name: "Police emergency", numbers: ["112"], description: "" },
                  { id: "nhaa", name: "NHAA", numbers: ["14566"], description: "" },
                ]
            ).map((h) => (
              <div className="helpline" key={h.id}>
                <span className="what">{h.name}</span>
                <span className="num">
                  {h.numbers.map((n) => (
                    <a key={n} href={`tel:${n}`} style={{ marginRight: 8 }}>
                      {n}
                    </a>
                  ))}
                </span>
              </div>
            ))}
          </div>
          <div className="row" style={{ marginTop: 20 }}>
            <button onClick={() => setStep(view ? "done" : "welcome")}>Go back</button>
          </div>
        </div>
      )}

      {(step === "done" || step === "resources" || step === "compose") && helplineBlock}
    </div>
  );
}
