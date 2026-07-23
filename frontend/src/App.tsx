import { useCallback, useEffect, useRef, useState } from "react";
import {
  convertCsv,
  convertJson,
  convertXml,
  DEFAULT_BASE,
  health,
  validateEdi,
  type ValidationResult,
} from "./api/client";
import { highlightJSON, highlightXML } from "./lib/edi";
import { SAMPLES } from "./samples";

const TXN_TYPES = ["auto", "837P", "837I", "835", "834", "270", "271", "276", "277"] as const;
type TxnType = (typeof TXN_TYPES)[number];
type Format = "json" | "xml" | "csv";

interface BatchRow {
  name: string;
  ok: boolean;
  badge: string;
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const CONVERT_MIN_MS = 2000;   // realistic loading time for conversions
const VALIDATE_MIN_MS = 2200;  // realistic loading time for auto-validation

type Result =
  | { kind: "placeholder" }
  | { kind: "loading"; label: string; source?: "convert" | "validate" }
  | { kind: "error"; title: string; detail: string }
  | { kind: "info"; title: string; detail: string }
  | { kind: "json" | "xml"; html: string; raw: string; badge: string }
  | { kind: "csv"; text: string; badge: string }
  | { kind: "validation"; report: ValidationResult }
  | { kind: "batch"; rows: BatchRow[]; raw: string; ext: string; badge: string };

function initialTheme(): "light" | "dark" {
  try {
    const s = localStorage.getItem("edi-theme");
    if (s === "light" || s === "dark") return s;
  } catch {
    /* ignore */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function parseCsv(text: string): string[][] {
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

export default function App() {
  const [theme, setTheme] = useState(initialTheme);
  const [status, setStatus] = useState<{ kind: string; text: string }>({
    kind: "checking",
    text: "Checking API…",
  });

  const [edi, setEdi] = useState("");
  const [fileName, setFileName] = useState("");
  const [apiBase, setApiBase] = useState(DEFAULT_BASE);
  const [format, setFormat] = useState<Format>("json");
  const [txnType, setTxnType] = useState<TxnType>("auto");
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const [result, setResult] = useState<Result>({ kind: "placeholder" });
  const [copied, setCopied] = useState(false);
  const [maximized, setMaximized] = useState(false);
  const [validity, setValidity] = useState<
    null | { kind: "valid" | "warn" | "error" | "checking"; label: string }
  >(null);

  const fileRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("edi-theme", theme); } catch { /* ignore */ }
  }, [theme]);

  const ping = useCallback(() => {
    setStatus({ kind: "checking", text: "Checking API…" });
    health(apiBase)
      .then((h) => setStatus({ kind: "online", text: `API online · v${h.version}` }))
      .catch(() => setStatus({ kind: "offline", text: "API offline" }));
  }, [apiBase]);

  useEffect(() => {
    const t = setTimeout(ping, 300);
    return () => clearTimeout(t);
  }, [ping]);

  // When the EDI content itself changes, drop any stale conversion result so the
  // fresh auto-validation can take the panel (but keep an existing validation view).
  useEffect(() => {
    setResult((prev) =>
      prev.kind === "validation" || prev.kind === "placeholder" ? prev : { kind: "placeholder" }
    );
  }, [edi]);

  // Auto-validate whenever EDI content changes (upload / drop / sample / paste),
  // debounced so it doesn't fire on every keystroke. Batch uploads are skipped.
  // The full report is shown in the output panel automatically, and a compact
  // chip appears in the Source header.
  useEffect(() => {
    if (batchFiles.length > 0 || !edi.trim()) {
      setValidity(null);
      return;
    }
    // Auto-validation only owns the result panel when the user hasn't run a
    // conversion for this content (guards against the two async flows racing).
    const validateCanOwn = (prev: Result) =>
      prev.kind === "placeholder" ||
      prev.kind === "validation" ||
      (prev.kind === "loading" && prev.source === "validate");

    const t = setTimeout(async () => {
      setValidity({ kind: "checking", label: "Validating…" });
      setResult((prev) =>
        validateCanOwn(prev) ? { kind: "loading", label: "Validating structure…", source: "validate" } : prev
      );
      try {
        // Hold the loading animation for a realistic minimum window (~2-3s).
        const [r] = await Promise.all([validateEdi(edi, fileName, apiBase), sleep(VALIDATE_MIN_MS)]);
        if (r.error_count > 0)
          setValidity({ kind: "error", label: `${r.error_count} error${r.error_count > 1 ? "s" : ""}` });
        else if (r.warning_count > 0)
          setValidity({ kind: "warn", label: `${r.warning_count} warning${r.warning_count > 1 ? "s" : ""}` });
        else setValidity({ kind: "valid", label: "Valid" });
        // Show the report automatically — but never overwrite a conversion.
        setResult((prev) => (validateCanOwn(prev) ? { kind: "validation", report: r } : prev));
      } catch {
        setValidity(null); // stay quiet if the API is unreachable
        setResult((prev) =>
          prev.kind === "loading" && prev.source === "validate" ? { kind: "placeholder" } : prev
        );
      }
    }, 600);
    return () => clearTimeout(t);
  }, [edi, fileName, apiBase, batchFiles.length]);

  // Esc closes the maximized result overlay.
  useEffect(() => {
    if (!maximized) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMaximized(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [maximized]);

  function loadFiles(files: FileList) {
    if (files.length > 1) {
      setBatchFiles(Array.from(files));
      setResult({ kind: "placeholder" });
      return;
    }
    setBatchFiles([]);
    const file = files[0];
    const reader = new FileReader();
    reader.onload = () => {
      setEdi(String(reader.result ?? ""));
      setFileName((prev) => prev || file.name);
    };
    reader.readAsText(file);
  }

  function clearAll() {
    setEdi("");
    setBatchFiles([]);
    setResult({ kind: "placeholder" });
  }

  function apiError(e: unknown): Result {
    const err = e as Error & { status?: number };
    if (err instanceof TypeError) {
      return { kind: "error", title: "Cannot reach the API",
        detail: `Network/CORS error contacting ${apiBase}. Confirm the backend is running.` };
    }
    return { kind: "error",
      title: "Request failed" + (err.status ? ` (HTTP ${err.status})` : ""),
      detail: (err.message || "Unknown error").slice(0, 400) };
  }

  async function convertSingle(fmt: Format) {
    setResult({ kind: "loading", label: `Converting to ${fmt.toUpperCase()}`, source: "convert" });
    try {
      // Hold the loading animation for a realistic minimum window.
      if (fmt === "json") {
        const [r] = await Promise.all([convertJson(edi, fileName, txnType, apiBase), sleep(CONVERT_MIN_MS)]);
        setResult({ kind: "json", html: highlightJSON(r.data),
          raw: JSON.stringify(r.data, null, 2), badge: r.transaction_type });
      } else if (fmt === "xml") {
        const [xml] = await Promise.all([convertXml(edi, fileName, txnType, apiBase), sleep(CONVERT_MIN_MS)]);
        setResult({ kind: "xml", html: highlightXML(xml), raw: xml, badge: "XML" });
      } else {
        const [csv] = await Promise.all([convertCsv(edi, fileName, txnType, apiBase), sleep(CONVERT_MIN_MS)]);
        setResult({ kind: "csv", text: csv, badge: "CSV" });
      }
    } catch (e) {
      setResult(apiError(e));
    }
  }

  async function runBatch(fmt: Format) {
    setResult({ kind: "loading", label: `Converting ${batchFiles.length} files to ${fmt.toUpperCase()}`, source: "convert" });
    const startedAt = performance.now();
    const rows: BatchRow[] = [];
    const parts: string[] = [];
    for (const f of batchFiles) {
      const text = await f.text();
      try {
        if (fmt === "json") {
          const r = await convertJson(text, f.name, txnType, apiBase);
          rows.push({ name: f.name, ok: true, badge: r.transaction_type });
          parts.push(JSON.stringify({ file: f.name, data: r.data }, null, 2));
        } else if (fmt === "xml") {
          const xml = await convertXml(text, f.name, txnType, apiBase);
          rows.push({ name: f.name, ok: true, badge: "XML" });
          const inner = xml.replace(/<\?xml[^>]*\?>\s*/, "");
          parts.push(`  <file name="${f.name}">\n${inner}\n  </file>`);
        } else {
          const csv = await convertCsv(text, f.name, txnType, apiBase);
          rows.push({ name: f.name, ok: true, badge: "CSV" });
          parts.push(`# ${f.name}\n${csv}`);
        }
      } catch (e) {
        const err = e as Error;
        rows.push({ name: f.name, ok: false, badge: (err.message || "failed").slice(0, 40) });
      }
    }
    let raw: string, ext: string;
    if (fmt === "json") { raw = `[\n${parts.join(",\n")}\n]`; ext = "json"; }
    else if (fmt === "xml") { raw = `<?xml version="1.0" encoding="UTF-8"?>\n<EdiBatch>\n${parts.join("\n")}\n</EdiBatch>\n`; ext = "xml"; }
    else { raw = parts.join("\n\n"); ext = "csv"; }
    // Keep the loading animation up for a realistic minimum window.
    const elapsed = performance.now() - startedAt;
    if (elapsed < CONVERT_MIN_MS) await sleep(CONVERT_MIN_MS - elapsed);
    const ok = rows.filter((r) => r.ok).length;
    setResult({ kind: "batch", rows, raw, ext, badge: `${ok}/${rows.length} converted` });
  }

  function run() {
    if (batchFiles.length > 0) return void runBatch(format);
    if (!edi.trim()) {
      setResult({ kind: "error", title: "No input", detail: "Paste some EDI, load a sample, or upload a file first." });
      return;
    }
    void convertSingle(format);
  }

  // ----- copy / download -------------------------------------------------- #
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
    a.download = (fileName.replace(/\.[^.]+$/, "") || "edi-result") + "." + dl.ext;
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

  const resultToolbar = (overlay: boolean) => (
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
      <div className="aurora" aria-hidden="true"><span className="a" /><span className="b" /><span className="c" /></div>

      <div className="shell">
        <header className="bar glass">
          <div className="brand">
            <div className="mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round"><path d="M3 12h4l2 5 4-10 2 5h6" /></svg>
            </div>
            <div><h1>EDI Converter</h1><p>X12 · Healthcare EDI</p></div>
          </div>
          <div className="bar-right">
            <div className={`status ${status.kind}`}><span className="dot" /><span>{status.text}</span></div>
            <button className="icon-btn" onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))} aria-label="Toggle theme">
              {theme === "dark" ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" /></svg>
              )}
            </button>
          </div>
        </header>

        <div className="grid">
          {/* Source */}
          <section className="panel glass">
            <div className="panel-head">
              <span className="step">1</span><h2>Source EDI</h2>
              {validity ? (
                <span className={`validity ${validity.kind}`}><span className="vdot" />{validity.label}</span>
              ) : (
                <span className="kicker">Paste · drop · upload</span>
              )}
            </div>

            <div className={`drop${drag ? " drag" : ""}`}
              onDragEnter={(e) => { e.preventDefault(); setDrag(true); }}
              onDragOver={(e) => e.preventDefault()}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files?.length) loadFiles(e.dataTransfer.files); }}>
              <textarea id="edi" spellCheck={false} value={edi}
                onChange={(e) => { setEdi(e.target.value); setBatchFiles([]); }}
                onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); run(); } }}
                placeholder="Paste raw X12 EDI here — an ISA*00*… interchange — or drop a .edi / .dat file, or load a sample below." />
              <div className="drop-hint">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" /></svg>
                drop file(s)
              </div>
            </div>

            <div className="chips">
              <span className="label">Samples</span>
              <button className="chip" onClick={() => { setBatchFiles([]); setEdi(SAMPLES["837"]); setResult({ kind: "placeholder" }); }}>837P Claim</button>
              <button className="chip" onClick={() => { setBatchFiles([]); setEdi(SAMPLES["835"]); setResult({ kind: "placeholder" }); }}>835 Remittance</button>
              <button className="chip upload" onClick={() => fileRef.current?.click()}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12m0-12l-4 4m4-4l4 4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" /></svg>
                Upload file(s)
              </button>
              <input ref={fileRef} type="file" accept=".edi,.dat,.txt,.x12" hidden multiple
                onChange={(e) => { if (e.target.files?.length) loadFiles(e.target.files); e.target.value = ""; }} />
            </div>
            {batchFiles.length > 0 && (
              <div className="batch-note">{batchFiles.length} files queued for batch conversion.</div>
            )}

            <div className="panel-head" style={{ marginTop: 2 }}><span className="step">2</span><h2>Options</h2></div>
            <div className="options">
              <div className="field">
                <label htmlFor="txn">Transaction type</label>
                <select id="txn" value={txnType} onChange={(e) => setTxnType(e.target.value as TxnType)}>
                  {TXN_TYPES.map((t) => <option key={t} value={t}>{t === "auto" ? "Auto-detect" : t}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="base">API base URL</label>
                <input id="base" type="text" spellCheck={false} value={apiBase} onChange={(e) => setApiBase(e.target.value)} />
              </div>
              <div className="field" style={{ gridColumn: "1 / -1" }}>
                <label htmlFor="fname">EDI file name (optional)</label>
                <input id="fname" type="text" spellCheck={false} placeholder="claim.dat" value={fileName} onChange={(e) => setFileName(e.target.value)} />
              </div>
            </div>

            <div className="panel-head" style={{ marginTop: 2 }}><span className="step">3</span><h2>Convert</h2></div>
            <div className="format-row">
              <span className="label">Output format</span>
              <div className="segment" role="group" aria-label="Output format">
                {(["json", "xml", "csv"] as Format[]).map((f) => (
                  <button key={f} className={`seg-btn${format === f ? " active" : ""}`} aria-pressed={format === f} onClick={() => setFormat(f)}>
                    {f.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
            <div className="actions">
              <button className="btn primary" onClick={run} disabled={result.kind === "loading"}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" /></svg>
                {result.kind === "loading" ? "Working…" : batchFiles.length > 0 ? `Convert ${batchFiles.length} files` : `Convert to ${format.toUpperCase()}`}
              </button>
              <button className="btn subtle" onClick={clearAll}>Clear</button>
            </div>
          </section>

          {/* Result */}
          <section className="panel glass result">
            <div className="panel-head">
              <span className="step">✓</span><h2>Result</h2>
              {resultToolbar(false)}
            </div>
            <div className="output"><ResultView result={result} /></div>
          </section>
        </div>

        <p className="footnote">Self-hosted EDI Converter — backend at <code>{apiBase}</code>. Files are processed in memory and not stored.</p>
      </div>

      {maximized && (
        <div className="overlay-backdrop" onClick={() => setMaximized(false)}>
          <div className="overlay-panel glass" onClick={(e) => e.stopPropagation()}>
            <div className="panel-head">
              <span className="step">✓</span><h2>Result</h2>
              {resultToolbar(true)}
            </div>
            <div className="output"><ResultView result={result} /></div>
          </div>
        </div>
      )}
    </>
  );
}

function ResultView({ result }: { result: Result }) {
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
    if (r.valid && r.issue_count === 0) {
      return <Centered tone="good" title="Valid — no issues found" subtitle="The X12 envelope structure passed all checks." />;
    }
    return (
      <div className="issues">
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
              <div className="issue-top"><span className={`sev ${sev}`}>{it.severity}</span>{loc && <span className="issue-loc">{loc}</span>}</div>
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
      <h3>Ready to convert</h3>
      <p>Load a sample or paste your EDI, pick a format, then Convert. JSON, XML, CSV, or a validation report will render here.</p>
    </div>
  );
}

function Centered({ tone, title, subtitle }: { tone: "muted" | "brand" | "good"; title: string; subtitle: string }) {
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
