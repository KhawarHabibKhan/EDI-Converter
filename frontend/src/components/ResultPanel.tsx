import { useEffect, useState } from "react";
import type { ValidationResult } from "../api/client";

export interface BatchRow {
  name: string;
  ok: boolean;
  badge: string;
}

/** Discriminated union describing everything the result panel can show.
 *  Shared by the Converter and FHIR pages (FHIR output uses the "json" kind). */
export type Result =
  | { kind: "placeholder" }
  | { kind: "loading"; label: string; source?: "convert" | "validate" }
  | { kind: "error"; title: string; detail: string }
  | { kind: "info"; title: string; detail: string }
  | { kind: "json" | "xml"; html: string; raw: string; badge: string }
  | { kind: "csv"; text: string; badge: string }
  | { kind: "validation"; report: ValidationResult }
  | { kind: "batch"; rows: BatchRow[]; raw: string; ext: string; badge: string };

export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cur = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { cur += '"'; i++; }
      else if (c === '"') q = false;
      else cur += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(cur); cur = ""; }
    else if (c === "\n") { row.push(cur); rows.push(row); row = []; cur = ""; }
    else if (c !== "\r") cur += c;
  }
  if (cur !== "" || row.length) { row.push(cur); rows.push(row); }
  return rows.filter((r) => r.some((c) => c !== ""));
}

/** The Result section + its toolbar (badge, maximize, copy, download) and the
 *  full-screen overlay. Both pages render this identically; only the `result`
 *  they feed it differs. `emptyTitle`/`emptyHint` customise the idle state. */
export function ResultPanel({
  result,
  fileName,
  emptyTitle = "Ready to convert",
  emptyHint = "Load a sample or paste your EDI, pick a format, then Convert. JSON, XML, CSV, or a validation report will render here.",
  downloadStem = "edi-result",
  onForward,
}: {
  result: Result;
  fileName: string;
  emptyTitle?: string;
  emptyHint?: string;
  downloadStem?: string;
  /** When provided, a "Forward to FHIR" button renders in the panel. It is
   *  enabled only for JSON/XML output (the formats the FHIR page can ingest). */
  onForward?: (text: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const [maximized, setMaximized] = useState(false);

  // Esc closes the maximized overlay.
  useEffect(() => {
    if (!maximized) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMaximized(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [maximized]);

  function downloadable(): { raw: string; ext: string; mime: string } | null {
    if (result.kind === "json") return { raw: result.raw, ext: "json", mime: "application/json" };
    if (result.kind === "xml") return { raw: result.raw, ext: "xml", mime: "application/xml" };
    if (result.kind === "csv") return { raw: result.text, ext: "csv", mime: "text/csv" };
    if (result.kind === "batch") return { raw: result.raw, ext: result.ext, mime: "text/plain" };
    if (result.kind === "validation")
      return { raw: JSON.stringify(result.report.issues, null, 2), ext: "json", mime: "application/json" };
    return null;
  }
  const dl = downloadable();

  function copy() {
    if (!dl) return;
    navigator.clipboard.writeText(dl.raw).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1100);
    });
  }
  function download() {
    if (!dl) return;
    const blob = new Blob([dl.raw], { type: dl.mime });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (fileName.replace(/\.[^.]+$/, "") || downloadStem) + "." + dl.ext;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const badge =
    result.kind === "json" || result.kind === "xml" || result.kind === "csv" || result.kind === "batch"
      ? result.badge
      : result.kind === "validation"
      ? result.report.valid ? "VALID" : `${result.report.error_count} errors`
      : "";

  const canMaximize = result.kind !== "placeholder" && result.kind !== "loading";

  // Only JSON/XML output is our-schema data the FHIR converter can ingest.
  const forwardable = result.kind === "json" || result.kind === "xml";
  function forward() {
    if (forwardable && onForward) onForward((result as { raw: string }).raw);
  }

  const toolbar = (overlay: boolean) => (
    <div className="res-toolbar" style={{ marginLeft: "auto" }}>
      {badge && <span className="badge">{badge}</span>}
      {!overlay && (
        <button className="mini" onClick={() => setMaximized(true)} disabled={!canMaximize} title="Maximize">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M8 3H5a2 2 0 00-2 2v3M16 3h3a2 2 0 012 2v3M8 21H5a2 2 0 01-2-2v-3M16 21h3a2 2 0 002-2v-3" /></svg>
        </button>
      )}
      <button className="mini" onClick={copy} disabled={!dl} title="Copy">
        {copied ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="var(--good)" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" /></svg>
        )}
      </button>
      <button className="mini" onClick={download} disabled={!dl} title="Download">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" /></svg>
      </button>
      {overlay && (
        <button className="mini" onClick={() => setMaximized(false)} title="Close (Esc)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
        </button>
      )}
    </div>
  );

  return (
    <>
      <section className="panel glass result">
        <div className="panel-head">
          <span className="step">✓</span><h2>Result</h2>
          {toolbar(false)}
        </div>
        <div className="output">
          <ResultView result={result} emptyTitle={emptyTitle} emptyHint={emptyHint} />
        </div>
        {onForward && (
          <div className="forward-bar">
            <button
              className="btn forward-btn"
              onClick={forward}
              disabled={!forwardable}
              title={
                forwardable
                  ? "Send this output to the FHIR converter"
                  : "Only JSON or XML output can be forwarded to FHIR"
              }
            >
              Forward to FHIR
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </button>
          </div>
        )}
      </section>

      {maximized && (
        <div className="overlay-backdrop" onClick={() => setMaximized(false)}>
          <div className="overlay-panel glass" onClick={(e) => e.stopPropagation()}>
            <div className="panel-head">
              <span className="step">✓</span><h2>Result</h2>
              {toolbar(true)}
            </div>
            <div className="output">
              <ResultView result={result} emptyTitle={emptyTitle} emptyHint={emptyHint} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function ResultView({
  result,
  emptyTitle,
  emptyHint,
}: {
  result: Result;
  emptyTitle: string;
  emptyHint: string;
}) {
  if (result.kind === "json" || result.kind === "xml") {
    return <pre dangerouslySetInnerHTML={{ __html: result.html }} />;
  }
  if (result.kind === "csv") {
    const rows = parseCsv(result.text);
    if (!rows.length) return <Centered tone="muted" title="Empty" subtitle="No CSV rows were produced." />;
    const [head, ...body] = rows;
    return (
      <table className="grid-table">
        <thead><tr>{head.map((h, i) => <th key={i}>{h}</th>)}</tr></thead>
        <tbody>{body.map((r, i) => <tr key={i}>{head.map((_, j) => <td key={j}>{r[j] ?? ""}</td>)}</tr>)}</tbody>
      </table>
    );
  }
  if (result.kind === "validation") {
    const r = result.report;
    const scope =
      (r.snip_level ? `SNIP level ${r.snip_level}` : "") +
      (r.transaction_type ? ` · ${r.transaction_type}` : "");
    if (r.valid && r.issue_count === 0) {
      return (
        <Centered
          tone="good"
          title="Valid — no issues found"
          subtitle={`Passed all checks${scope ? ` (${scope.trim()})` : ""}.`}
        />
      );
    }
    return (
      <div className="issues">
        {scope && <div className="issues-scope">Validated to {scope.trim()}</div>}
        <div className="summary">
          <div className="stat e"><b>{r.error_count}</b><span>Errors</span></div>
          <div className="stat w"><b>{r.warning_count}</b><span>Warnings</span></div>
          <div className="stat g"><b>{r.issue_count}</b><span>Total</span></div>
        </div>
        {r.issues.map((it, i) => {
          const sev = it.severity.toLowerCase();
          const loc = [it.segment && `seg ${it.segment}`, it.position ? `#${it.position}` : ""].filter(Boolean).join(" · ");
          return (
            <div key={i} className={`issue ${sev}`}>
              <div className="issue-top">
                {it.stage === "fhir" ? (
                  <span className="snip-badge fhir">FHIR</span>
                ) : it.level != null ? (
                  <span className={`snip-badge l${it.level}`}>L{it.level}</span>
                ) : null}
                <span className={`sev ${sev}`}>{it.severity}</span>
                {loc && <span className="issue-loc">{loc}</span>}
              </div>
              <div className="issue-msg">{it.message}</div>
            </div>
          );
        })}
      </div>
    );
  }
  if (result.kind === "batch") {
    return (
      <table className="grid-table">
        <thead><tr><th>File</th><th>Status</th><th>Type / Error</th></tr></thead>
        <tbody>
          {result.rows.map((r, i) => (
            <tr key={i}>
              <td>{r.name}</td>
              <td className={r.ok ? "pill-ok" : "pill-bad"}>{r.ok ? "OK" : "FAILED"}</td>
              <td>{r.badge}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  if (result.kind === "loading") {
    return (<div className="placeholder"><div className="spinner" /><h3>{result.label}</h3><p>Talking to the converter…</p></div>);
  }
  if (result.kind === "error") {
    return (
      <div className="placeholder">
        <div className="ph-mark" style={{ color: "var(--crit)", background: "color-mix(in srgb, var(--crit) 14%, transparent)" }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round"><path d="M12 8v5M12 16.5v.5" /><path d="M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" /></svg>
        </div>
        <h3>{result.title}</h3><p>{result.detail}</p>
      </div>
    );
  }
  if (result.kind === "info") {
    return <Centered tone="brand" title={result.title} subtitle={result.detail} />;
  }
  return (
    <div className="placeholder">
      <div className="ph-mark"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"><path d="M3 12h4l2 5 4-10 2 5h6" /></svg></div>
      <h3>{emptyTitle}</h3>
      <p>{emptyHint}</p>
    </div>
  );
}

export function Centered({ tone, title, subtitle }: { tone: "muted" | "brand" | "good"; title: string; subtitle: string }) {
  const style =
    tone === "good" ? { color: "var(--good)", background: "color-mix(in srgb, var(--good) 14%, transparent)" }
    : tone === "brand" ? { color: "var(--accent)", background: "var(--accent-soft)" }
    : { color: "var(--ink-mute)", background: "var(--glass-inner)" };
  return (
    <div className="placeholder">
      <div className="ph-mark" style={style}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"><path d="M9 12l2 2 4-4" /><path d="M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z" /></svg>
      </div>
      <h3>{title}</h3><p>{subtitle}</p>
    </div>
  );
}
