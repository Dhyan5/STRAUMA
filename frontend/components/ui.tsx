/**
 * Shared presentational pieces.
 *
 * `Disclaimer` is the one component every page is required to render. It takes
 * the string from the backend when it has one and falls back to a hard-coded
 * copy of the mandated wording, because a screen that renders before the config
 * call resolves must still carry the notice.
 */

"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

export const FALLBACK_DISCLAIMER =
  "Prototype for demonstration purposes. Not a diagnostic tool. All risk flags are reviewed by trained personnel.";

export function Disclaimer({ text }: { text?: string | null }) {
  return <p className="disclaimer">{text || FALLBACK_DISCLAIMER}</p>;
}

export function Band({ value }: { value: string }) {
  return <span className={`band ${value}`}>{value}</span>;
}

export function BandBar({ value, counts }: { value: string; counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="bar-row">
      <span className="label">
        <Band value={value} />
      </span>
      <span className="track">
        <span
          className="fill"
          style={{
            width: `${((counts[value] ?? 0) / total) * 100}%`,
            background:
              value === "Low"
                ? "#3f8f74"
                : value === "Moderate"
                  ? "#c08a2e"
                  : value === "High"
                    ? "#c96a1f"
                    : "#8f2020",
          }}
        />
      </span>
      <span className="n">{counts[value] ?? 0}</span>
    </div>
  );
}

export function Stat({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="stat">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}

export function Notice({
  kind = "info",
  children,
}: {
  kind?: "info" | "ok" | "warn" | "error";
  children: ReactNode;
}) {
  return <div className={`notice ${kind}`}>{children}</div>;
}

/** The refusal surface. Used wherever the backend says no. */
export function Refused({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="refused" role="alert">
      <strong>{title}</strong>
      {children}
    </div>
  );
}

/**
 * Quick exit. Replaces the entire document with a neutral page and clears the
 * session token. No confirmation, no animation, no delay, and the back button
 * does not return to the form.
 */
export function QuickExit({ onExit }: { onExit?: () => void }) {
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!done) return;
    const stop = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", stop);
    // Replace the history entry so Back does not land on the intake form.
    window.history.replaceState(null, "", window.location.pathname);
    return () => window.removeEventListener("beforeunload", stop);
  }, [done]);

  if (done) {
    return (
      <div className="exited">
        <p>
          You have left this page. Nothing was sent. If you need to talk to
          someone, you can call <strong>112</strong> or{" "}
          <strong>Tele MANAS on 14416</strong> at any time, free of charge.
        </p>
      </div>
    );
  }

  return (
    <button
      type="button"
      className="quick-exit"
      onClick={() => {
        try {
          window.sessionStorage.clear();
        } catch {
          /* storage disabled; the page is being replaced anyway */
        }
        onExit?.();
        setDone(true);
      }}
    >
      Quick exit
    </button>
  );
}

export function TopBar({ right }: { right?: ReactNode }) {
  return (
    <header className="topbar">
      <div className="brand">
        NHAA 14566 <span>&middot; Stress &amp; Trauma Assessment &middot; prototype</span>
      </div>
      <nav>
        <Link href="/">Home</Link>
        <Link href="/victim">Victim portal</Link>
        <Link href="/staff">Staff</Link>
        <Link href="/law">Law enforcement</Link>
        {right}
      </nav>
    </header>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return <p className="muted">{what}...</p>;
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="notice error" role="alert">
      {message}
    </div>
  );
}

export function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
