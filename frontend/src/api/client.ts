// Backend calls, bound to the "API base URL" field. Defaults to the Vite env.
export const DEFAULT_BASE =
  import.meta.env.VITE_API_URL ?? "http://localhost:5080";

function trimBase(base: string): string {
  return (base || DEFAULT_BASE).replace(/\/+$/, "");
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface JsonResponse {
  transaction_type: string;
  file_name: string;
  data: unknown;
  issues: unknown[];
}

export async function health(base: string): Promise<HealthResponse> {
  const res = await fetch(`${trimBase(base)}/health`);
  if (!res.ok) throw new Error(`Health check failed (${res.status})`);
  return res.json();
}

/** Convert EDI text to JSON. Text is sent as a Blob to the multipart endpoint. */
export async function convertJson(
  text: string,
  fileName: string,
  type: string,
  base: string
): Promise<JsonResponse> {
  const form = new FormData();
  const name = fileName?.trim() || "claim.edi";
  form.append("file", new Blob([text], { type: "text/plain" }), name);

  const res = await fetch(
    `${trimBase(base)}/edi/json?type=${encodeURIComponent(type)}`,
    { method: "POST", body: form }
  );
  if (!res.ok) {
    let detail = `Conversion failed (${res.status})`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* keep default */
    }
    const err = new Error(detail) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json();
}

async function postText(
  path: string,
  text: string,
  fileName: string,
  base: string
): Promise<string> {
  const form = new FormData();
  form.append("file", new Blob([text], { type: "text/plain" }), fileName?.trim() || "claim.edi");
  const res = await fetch(`${trimBase(base)}${path}`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* keep default */
    }
    const err = new Error(detail) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.text();
}

/** Convert EDI text to XML. Returns the raw XML document as text. */
export function convertXml(text: string, fileName: string, type: string, base: string) {
  return postText(`/edi/xml?type=${encodeURIComponent(type)}`, text, fileName, base);
}

/** Convert EDI text to CSV. Returns the raw CSV text. */
export function convertCsv(text: string, fileName: string, type: string, base: string) {
  return postText(`/edi/csv?type=${encodeURIComponent(type)}`, text, fileName, base);
}

export interface ValidationResult {
  file_name: string;
  valid: boolean;
  error_count: number;
  warning_count: number;
  issue_count: number;
  issues: { severity: string; message: string; segment: string; position: number }[];
}

/** Validate EDI structure. Returns the issue report. */
export async function validateEdi(
  text: string,
  fileName: string,
  base: string
): Promise<ValidationResult> {
  const raw = await postText("/edi/validate", text, fileName, base);
  return JSON.parse(raw);
}
