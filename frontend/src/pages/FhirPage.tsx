import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { convertFhir, DEFAULT_BASE, health, validateFhir } from "../api/client";
import { highlightJSON } from "../lib/edi";
import { SAMPLES } from "../samples";
import { useTheme } from "../lib/theme";
import { Header } from "../components/Header";
import { ResultPanel, type Result } from "../components/ResultPanel";

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const CONVERT_MIN_MS = 2000; // realistic loading window, matches the v1 page

/** Derive a "FHIR · <ResourceType>" badge from the returned Bundle. */
function fhirBadge(bundle: unknown): string {
  try {
    const entries = (bundle as { entry?: { resource?: { resourceType?: string } }[] }).entry ?? [];
    const primary =
      entries.map((e) => e.resource?.resourceType).find((t) => t === "Claim" || t === "ExplanationOfBenefit") ??
      entries[entries.length - 1]?.resource?.resourceType;
    return primary ? `FHIR · ${primary}` : "FHIR Bundle";
  } catch {
    return "FHIR Bundle";
  }
}

export default function FhirPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [theme, toggleTheme] = useTheme();
  const [status, setStatus] = useState<{ kind: string; text: string }>({
    kind: "checking",
    text: "Checking API…",
  });

  const [input, setInput] = useState("");
  const [fileName, setFileName] = useState("");
  const [apiBase, setApiBase] = useState(DEFAULT_BASE);
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

  function loadFile(files: FileList) {
    const file = files[0];
    const reader = new FileReader();
    reader.onload = () => {
      setInput(String(reader.result ?? ""));
      setFileName((prev) => prev || file.name);
    };
    reader.readAsText(file);
  }

  function clearAll() {
    setInput("");
    setResult({ kind: "placeholder" });
    setValidity(null);
  }

  function apiError(e: unknown): Result {
    const err = e as Error & { status?: number };
    if (err instanceof TypeError) {
      return {
        kind: "error",
        title: "Cannot reach the API",
        detail: `Network/CORS error contacting ${apiBase}. Confirm the backend is running.`,
      };
    }
    return {
      kind: "error",
      title: "Conversion failed" + (err.status ? ` (HTTP ${err.status})` : ""),
      detail: (err.message || "Unknown error").slice(0, 400),
    };
  }

  // `src` defaults to the textarea, but forwarded content passes it explicitly
  // (the input state update from a hand-off isn't visible synchronously here).
  async function run(src: string = input, name: string = fileName) {
    if (!src.trim()) {
      setResult({
        kind: "error",
        title: "No input",
        detail: "Paste EDI/JSON/XML, load a sample, or upload a file first.",
      });
      return;
    }
    setResult({ kind: "loading", label: "Building FHIR Bundle", source: "convert" });
    setValidity(null);
    try {
      const [raw] = await Promise.all([convertFhir(src, name, apiBase), sleep(CONVERT_MIN_MS)]);
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        parsed = raw;
      }
      const pretty = typeof parsed === "string" ? raw : JSON.stringify(parsed, null, 2);
      setResult({ kind: "json", html: highlightJSON(parsed), raw: pretty, badge: fhirBadge(parsed) });
      void runFhirValidation(src, name);
    } catch (e) {
      setResult(apiError(e));
    }
  }

  // After a successful conversion, validate the generated Bundle's FHIR R4
  // structure automatically and surface a compact chip in the Source header.
  async function runFhirValidation(src: string = input, name: string = fileName) {
    setValidity({ kind: "checking", label: "Validating FHIR…" });
    try {
      const r = await validateFhir(src, name, apiBase);
      if (r.error_count > 0)
        setValidity({ kind: "error", label: `${r.error_count} FHIR error${r.error_count > 1 ? "s" : ""}` });
      else if (r.warning_count > 0)
        setValidity({ kind: "warn", label: `${r.warning_count} warning${r.warning_count > 1 ? "s" : ""}` });
      else setValidity({ kind: "valid", label: "Valid FHIR R4" });
    } catch {
      setValidity(null); // stay quiet if validation can't be reached
    }
  }

  // Receive a "Forward to FHIR" hand-off from the Converter page: only prefill
  // the input (do NOT auto-convert — the user clicks Convert themselves). Clear
  // the router state so a refresh/back won't refire.
  useEffect(() => {
    const st = location.state as { forwardedInput?: string; forwardedName?: string } | null;
    if (st?.forwardedInput) {
      setInput(st.forwardedInput);
      setFileName(st.forwardedName || "forwarded.json");
      setResult({ kind: "placeholder" });
      setValidity(null);
      navigate("/fhir", { replace: true });
    }
    // Run once on mount; forwarded payload arrives via router navigation state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="shell">
      <Header theme={theme} onToggleTheme={toggleTheme} status={status} />

      <div className="grid">
        {/* Source */}
        <section className="panel glass">
          <div className="panel-head">
            <span className="step">1</span><h2>Source</h2>
            {validity ? (
              <span className={`validity ${validity.kind}`}><span className="vdot" />{validity.label}</span>
            ) : (
              <span className="kicker">EDI · JSON · XML</span>
            )}
          </div>

          <div className={`drop${drag ? " drag" : ""}`}
            onDragEnter={(e) => { e.preventDefault(); setDrag(true); }}
            onDragOver={(e) => e.preventDefault()}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files?.length) loadFile(e.dataTransfer.files); }}>
            <textarea id="fhir-input" spellCheck={false} value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); run(); } }}
              placeholder="Paste X12 EDI, or an EDI-Converter JSON / XML export — or drop a .edi / .dat / .json / .xml file, or load a sample below." />
            <div className="drop-hint">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" /></svg>
              drop file
            </div>
          </div>

          <div className="chips">
            <span className="label">Samples</span>
            <button className="chip" onClick={() => { setInput(SAMPLES["837"]); setResult({ kind: "placeholder" }); }}>837P Claim</button>
            <button className="chip upload" onClick={() => fileRef.current?.click()}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12m0-12l-4 4m4-4l4 4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" /></svg>
              Upload file
            </button>
            <input ref={fileRef} type="file" accept=".edi,.dat,.txt,.x12,.json,.xml" hidden
              onChange={(e) => { if (e.target.files?.length) loadFile(e.target.files); e.target.value = ""; }} />
          </div>

          <div className="panel-head" style={{ marginTop: 2 }}><span className="step">2</span><h2>Options</h2></div>
          <div className="options">
            <div className="field">
              <label htmlFor="fhir-base">API base URL</label>
              <input id="fhir-base" type="text" spellCheck={false} value={apiBase} onChange={(e) => setApiBase(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="fhir-fname">File name (optional)</label>
              <input id="fhir-fname" type="text" spellCheck={false} placeholder="claim.edi" value={fileName} onChange={(e) => setFileName(e.target.value)} />
            </div>
          </div>

          <div className="panel-head" style={{ marginTop: 2 }}><span className="step">3</span><h2>Convert</h2></div>
          <div className="format-row">
            <span className="label">Output format</span>
            <div className="segment" role="group" aria-label="Output format">
              <button className="seg-btn active" aria-pressed={true} disabled>FHIR R4 · Bundle</button>
            </div>
          </div>
          <p className="fhir-note">
            Transaction type is auto-detected. Output is a FHIR R4 <code>Bundle</code> (<code>type: collection</code>):
            837→<code>Claim</code>, 835→<code>ExplanationOfBenefit</code>, 834→<code>Coverage</code>,
            270/271→<code>CoverageEligibility</code>, 276/277→<code>Task</code>. The Bundle is auto-validated against base FHIR R4.
          </p>
          <div className="actions">
            <button className="btn primary" onClick={() => run()} disabled={result.kind === "loading"}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" /></svg>
              {result.kind === "loading" ? "Working…" : "Convert to FHIR"}
            </button>
            <button className="btn subtle" onClick={clearAll}>Clear</button>
          </div>
        </section>

        {/* Result */}
        <ResultPanel
          result={result}
          fileName={fileName}
          downloadStem="fhir-bundle"
          emptyTitle="Ready to convert to FHIR"
          emptyHint="Load a sample, paste EDI/JSON/XML, or upload a file, then Convert. A FHIR R4 Bundle will render here."
        />
      </div>

      <p className="footnote">FHIR Converter (v2) — backend at <code>{apiBase}</code>. Files are processed in memory and not stored.</p>
    </div>
  );
}
