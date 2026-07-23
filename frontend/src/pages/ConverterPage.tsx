import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  convertCsv,
  convertJson,
  convertXml,
  DEFAULT_BASE,
  health,
  validateEdi,
} from "../api/client";
import { highlightJSON, highlightXML } from "../lib/edi";
import { SAMPLES } from "../samples";
import { useTheme } from "../lib/theme";
import { Header } from "../components/Header";
import { ResultPanel, type BatchRow, type Result } from "../components/ResultPanel";

const TXN_TYPES = ["auto", "837P", "837I", "835", "834", "270", "271", "276", "277"] as const;
type TxnType = (typeof TXN_TYPES)[number];
type Format = "json" | "xml" | "csv";

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const CONVERT_MIN_MS = 2000;   // realistic loading time for conversions
const VALIDATE_MIN_MS = 2200;  // realistic loading time for auto-validation

export default function ConverterPage() {
  const navigate = useNavigate();
  const [theme, toggleTheme] = useTheme();
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
  const [validity, setValidity] = useState<
    null | { kind: "valid" | "warn" | "error" | "checking"; label: string }
  >(null);

  const fileRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

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

  // Hand the current JSON/XML output to the FHIR converter and switch pages.
  // The FHIR page reads the payload from router state and auto-converts.
  function forwardToFhir(text: string) {
    navigate("/fhir", { state: { forwardedInput: text, forwardedName: fileName } });
  }

  return (
    <div className="shell">
      <Header theme={theme} onToggleTheme={toggleTheme} status={status} />

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
        <ResultPanel result={result} fileName={fileName} onForward={forwardToFhir} />
      </div>

      <p className="footnote">Self-hosted EDI Converter — backend at <code>{apiBase}</code>. Files are processed in memory and not stored.</p>
    </div>
  );
}
