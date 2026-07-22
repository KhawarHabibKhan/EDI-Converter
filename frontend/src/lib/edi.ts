// Small client-side EDI helpers: JSON syntax highlighting + type detection.

export function escapeHtml(s: string): string {
  return s.replace(/[&<>]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[m] as string));
}

const TOKEN =
  /("(?:\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(?:\s*:)?|\b(?:true|false)\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

/** Return JSON as syntax-highlighted, HTML-escaped markup. */
export function highlightJSON(value: unknown): string {
  const json = escapeHtml(JSON.stringify(value, null, 2));
  return json.replace(TOKEN, (m) => {
    let cls = "tok-num";
    if (/^&quot;|^"/.test(m)) cls = /:$/.test(m) ? "tok-key" : "tok-str";
    else if (m === "true" || m === "false") cls = "tok-bool";
    else if (m === "null") cls = "tok-null";
    return `<span class="${cls}">${m}</span>`;
  });
}

/** Return XML as syntax-highlighted, HTML-escaped markup (tags accented). */
export function highlightXML(xml: string): string {
  const escaped = escapeHtml(xml);
  // Highlight the declaration, tags, and text-bearing tag names.
  return escaped
    .replace(/(&lt;\?[\s\S]*?\?&gt;)/g, '<span class="tok-null">$1</span>')
    .replace(/(&lt;\/?)([A-Za-z_][\w.-]*)(\/?&gt;)/g,
      (_m, open, name, close) =>
        `${open}<span class="tok-key">${name}</span>${close}`);
}

/** Detect the X12 transaction type from the ST segment (+ GS version). */
export function detectType(edi: string): string {
  const st = edi.match(/ST\s*\*\s*(\d{3})/);
  const code = st?.[1];
  if (!code) return "unknown";
  if (code === "837") return /X223/.test(edi) ? "837I" : "837P";
  return code; // 835, 834, 271, 277, …
}
