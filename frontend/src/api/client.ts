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

/** Convert EDI / our JSON / our XML to a FHIR R4 Bundle (v2).
 *  Returns the raw FHIR JSON document as text. Type is auto-detected server-side. */
export function convertFhir(text: string, fileName: string, base: string) {
  return postText("/edi/fhir", text, fileName, base);
}

/** Validate the generated FHIR Bundle's R4 structure (v2). Returns the same
 *  report shape as validateEdi so the UI renders it with one component. */
export async function validateFhir(
  text: string,
  fileName: string,
  base: string
): Promise<ValidationResult> {
  const raw = await postText("/edi/fhir/validate", text, fileName, base);
  return JSON.parse(raw);
}

export interface ValidationResult {
  file_name: string;
  transaction_type?: string | null;
  snip_level?: number;
  valid: boolean;
  error_count: number;
  warning_count: number;
  issue_count: number;
  issues: { severity: string; message: string; segment: string; position: number; level?: number; stage?: string }[];
}

/** Validate EDI through the WEDI SNIP levels (cumulative). `snipLevel` omitted
 *  = server default (highest implemented). Returns the issue report. */
export async function validateEdi(
  text: string,
  fileName: string,
  base: string,
  snipLevel?: number
): Promise<ValidationResult> {
  const path =
    snipLevel != null ? `/edi/validate?snip_level=${snipLevel}` : "/edi/validate";
  const raw = await postText(path, text, fileName, base);
  return JSON.parse(raw);
}
