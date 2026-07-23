# 8 — Frontend Plan

> **Project name:** EDI-Converter
> **Last updated:** 2026-07-21
>
> Concrete build plan for the frontend. Follow `5-design.md` for all visual
> tokens and `3-rules.md` for conventions. This document says *exactly what to
> build* in `frontend/`.

---

## 8.1 Goal

A single-page React app where a user uploads an EDI file, picks the transaction
type and output format, and views/downloads the converted result — calling our
own backend (not datainsight).

---

## 8.2 Folder layout (target)

```
frontend/
├── Dockerfile
├── package.json
├── vite.config.ts
├── tailwind.config.ts        # design tokens from 5-design.md
├── index.html
└── src/
    ├── main.tsx              # React entry
    ├── App.tsx               # page layout + orchestration
    ├── types.ts              # TransactionType, OutputFormat, ConversionResult
    ├── api/
    │   └── client.ts         # convertEdi(), validateEdi(), health()
    ├── components/
    │   ├── Header.tsx
    │   ├── ControlsBar.tsx   # wraps TypeSelector + FormatToggle
    │   ├── TypeSelector.tsx
    │   ├── FormatToggle.tsx
    │   ├── FileUpload.tsx    # drag & drop + <input type=file>
    │   ├── ResultViewer.tsx  # JSON tree, copy, download
    │   ├── IssueList.tsx     # validation issues (Phase 6)
    │   └── ErrorBanner.tsx
    ├── hooks/
    │   └── useConvert.ts     # state machine for the convert flow
    └── styles/
        └── index.css         # Tailwind directives + tokens
```

---

## 8.3 State model

```ts
type TransactionType = "auto" | "837P" | "837I" | "835" | "834" | "270" | "271" | "276" | "277";
type Format = "json" | "xml" | "csv";

// The result panel is a discriminated union (implemented in App.tsx):
type Result =
  | { kind: "placeholder" }
  | { kind: "loading"; label: string; source?: "convert" | "validate" }
  | { kind: "error" | "info"; title: string; detail: string }
  | { kind: "json" | "xml"; html: string; raw: string; badge: string }
  | { kind: "csv"; text: string; badge: string }
  | { kind: "validation"; report: ValidationResult }
  | { kind: "batch"; rows; raw: string; ext: string; badge: string };

interface AppState {
  edi: string; fileName: string; apiBase: string;
  txnType: TransactionType;            // default "auto"
  format: Format;                      // default "json"
  batchFiles: File[];                  // multi-file batch
  result: Result;
  validity: { kind: "valid"|"warn"|"error"|"checking"; label } | null; // auto-validate chip
  maximized: boolean;                  // result overlay open
}
```

Flow:
```
add file/paste → (debounce 600ms) → auto-validate: loading(source=validate)
                → validation report + validity chip
pick format + Convert → loading(source=convert) → JSON/XML/CSV result
```
- **Loading windows:** min ~2 s (convert) / ~2–3 s (validate) via
  `Promise.all([apiCall, sleep()])`.
- **Race guard:** auto-validation owns the panel only when it's not showing a
  conversion (checks `source` on the loading state).

---

## 8.4 Components & responsibilities

| Component | Props / role | Key states |
|-----------|-------------|------------|
| `Header` | title, theme toggle (later) | — |
| `ControlsBar` | holds type + format controls | — |
| `TypeSelector` | `value`, `onChange` — dropdown of 7 options | default "Auto-detect" |
| `FormatToggle` | segmented output-format selector: JSON / XML / CSV | active pill |
| `ConvertButton` | single primary action — converts to the selected format | idle / loading |
| `FileUpload` | dropzone + paste + multi-file (batch) | idle / dragover / loading |
| Result viewer | formatted JSON/XML/CSV, copy + download | empty / loading / populated |
| **Validity chip** | auto-validation status in Source header | valid / warn / error / checking |
| **Maximize overlay** | expands result to a large centered glass panel | open / closed (Esc/backdrop) |
| Issue list | severity icon + message + segment/line (validation report) | empty / has-issues |

> No separate "Validate" button — validation runs automatically on file add
> (the button was removed as redundant).

### Interaction rules (from `5-design.md`)
- Dropzone highlights on dragover; also clickable to open file picker.
- Spinner appears within 100ms of upload.
- On error, **keep** the file and selections (don't reset the form).
- Download button names the file after the input (`claim.dat → claim.json`).
- `aria-live` region announces result/error for screen readers.

---

## 8.5 API client (`src/api/client.ts`)

```ts
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:5080";

// Pasted/sample text and uploaded files are all sent as a Blob to the
// multipart endpoint, so no backend text-body support is required.
export async function convertEdi(
  text: string, fileName: string, type: TransactionType, format: OutputFormat
): Promise<unknown> {
  const form = new FormData();
  form.append("file", new Blob([text], { type: "text/plain" }), fileName || "claim.edi");
  const path = format === "xml" ? "/edi/xml" : "/edi/json";
  const res = await fetch(`${BASE}${path}?type=${type}`, { method: "POST", body: form });
  if (!res.ok) throw new Error((await res.json()).detail ?? "Conversion failed");
  return format === "xml" ? res.text() : res.json();
}

export const health = () => fetch(`${BASE}/health`).then(r => r.json());
```

`VITE_API_URL` comes from `.env` so the backend URL is not hard-coded.

---

## 8.6 Layout (from design doc)

```
Header (logo · "EDI Converter" · theme toggle)
────────────────────────────────────────────────
ControlsBar:  [ Transaction type ▼ ]   Format: [ JSON | XML ]  → Convert
FileUpload:   ⬍ drag & drop EDI file (.edi .dat .txt) ⬍
ResultViewer: detected: 837P   [Copy] [Download]
              { formatted JSON ... }
```
- Max width 1100px, centered; single column on mobile.
- Result panel scrolls internally (`overflow: auto`), never breaks page layout.

---

## 8.7 Build order (maps to phases)

1. **Phase 0:** Vite + React + TS + Tailwind scaffold; `Header`; call `/health`
   and show backend status.
2. **Phase 1:** upload/paste/sample + `FormatToggle` (JSON / XML) + single
   **Convert** button + result viewer (highlighted) + copy/download — convert a
   real 837P to JSON or XML.
3. **Phase 2:** `TypeSelector` (7 options) wired to the request.
4. **Phase 6:** add a "Validation" action + `IssueList`.
5. **Phase 7:** add a "CSV" format option (download CSV); optional batch UI.
6. **Phase 8:** apply full design system, states, responsive, dark mode.

---

## 8.8 package.json (starting deps)
```
react, react-dom
vite, @vitejs/plugin-react, typescript
tailwindcss, postcss, autoprefixer
vitest, @testing-library/react   (dev)
```
(Optional: a small JSON-tree viewer component; otherwise render with a custom
collapsible + monospace styling.)

## 8.9 Dockerfile (shape)
```dockerfile
# build
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
RUN npm run build
# serve
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

---

## 8.10 Definition of done (frontend)
- [ ] Upload → convert → view → download works for 837P.
- [ ] All 7 type options selectable; auto-detect is default.
- [ ] JSON and XML formats both work (pick format, then Convert).
- [ ] Errors show in `ErrorBanner` without losing the user's file/selection.
- [ ] Keyboard accessible; WCAG AA contrast; `aria-live` results.
- [ ] Responsive (mobile single-column, desktop two-column controls).
- [ ] No hard-coded backend URL (uses `VITE_API_URL`).
- [ ] Shows "Files are processed in memory and not stored." note.
