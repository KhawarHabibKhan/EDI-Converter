# 5 — Design System

> **Project name:** EDI-Converter
> **Last updated:** 2026-07-21
>
> Visual and UX rules for the frontend. Healthcare tooling should feel
> **clean, calm, trustworthy, and precise** — not flashy.

---

## 5.1 Color & Theme

Healthcare palette: trustworthy blues/teals, generous neutrals, clear semantic
status colors. Defined as tokens so they can drop straight into Tailwind config.

### Brand
| Token | Hex | Use |
|-------|-----|-----|
| `--brand-primary` | `#0F766E` (teal-700) | Primary buttons, active states, links |
| `--brand-primary-hover` | `#0D5F58` | Hover on primary |
| `--brand-accent` | `#2563EB` (blue-600) | Secondary accent, highlights |

### Neutrals (light theme)
| Token | Hex | Use |
|-------|-----|-----|
| `--bg` | `#F8FAFC` (slate-50) | Page background |
| `--surface` | `#FFFFFF` | Cards, panels, upload area |
| `--border` | `#E2E8F0` (slate-200) | Dividers, input borders |
| `--text` | `#0F172A` (slate-900) | Primary text |
| `--text-muted` | `#64748B` (slate-500) | Secondary text, labels |

### Semantic / status
| Token | Hex | Use |
|-------|-----|-----|
| `--success` | `#16A34A` (green-600) | Valid file, success toast |
| `--warning` | `#D97706` (amber-600) | Warnings in validation |
| `--error` | `#DC2626` (red-600) | Errors, invalid EDI |
| `--info` | `#2563EB` (blue-600) | Informational notes |

### Dark theme (later phase — define now for consistency)
| Token | Hex |
|-------|-----|
| `--bg` | `#0F172A` (slate-900) |
| `--surface` | `#1E293B` (slate-800) |
| `--border` | `#334155` (slate-700) |
| `--text` | `#F1F5F9` (slate-100) |
| `--text-muted` | `#94A3B8` (slate-400) |
| brand stays teal, slightly lightened (`#14B8A6`) for contrast |

**Contrast rule:** all text must meet **WCAG AA** (4.5:1 for body, 3:1 for large
text). Never rely on color alone to signal status — pair with an icon/label.

---

## 5.2 Front (Layout & Components)

### Overall layout
```
┌───────────────────────────────────────────────────────────┐
│  Header:  logo · "EDI Converter" · (theme toggle)          │
├───────────────────────────────────────────────────────────┤
│                                                             │
│   ┌───────────────── Controls card ─────────────────────┐  │
│   │  [ Transaction type ▼ ]   Format: [ JSON | XML ]  │  │
│   └──────────────────────────────────────────────────────┘ │
│                                                             │
│   ┌────────────── Upload dropzone ──────────────────────┐  │
│   │        Drag & drop EDI file, or click to browse       │  │
│   │              (.edi  .dat  .txt)                       │  │
│   └──────────────────────────────────────────────────────┘ │
│                                                             │
│   ┌───────────────── Result panel ─────────────────────┐   │
│   │  detected: 837P    [ Copy ] [ Download ]             │   │
│   │  { formatted, collapsible JSON ... }                 │   │
│   └──────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

### Component states (every interactive element defines all of these)
- **Default / Hover / Active / Focus (visible ring) / Disabled**
- Upload: **idle → dragover (highlight) → uploading (spinner) → success / error**
- Result: **empty ("no file yet") → loading → populated → error**

### Key components (map to `frontend/src/components/`)
- `FileUpload` — dropzone, shows file name + size once selected.
- `TypeSelector` — dropdown, default "Auto-detect".
- `FormatToggle` — segmented control for the **output format** (JSON / XML);
  the user selects it, then presses **Convert**.
- `ResultViewer` — monospace, syntax-highlighted, collapsible tree; copy +
  download.
- `ErrorBanner` — red surface, icon + message, dismissible.

### Spacing & shape
- Base spacing unit: **4px**; use multiples (8, 12, 16, 24, 32).
- Corner radius: **8px** cards, **6px** inputs/buttons.
- Card shadow: subtle (`0 1px 3px rgba(0,0,0,0.08)`), never heavy.
- Max content width: **1100px**, centered, comfortable side padding.

---

## 5.3 Typography

| Role | Font | Size | Weight |
|------|------|------|--------|
| App title | Inter / system sans | 20px | 600 |
| Section headings | Inter | 16px | 600 |
| Body / labels | Inter | 14px | 400–500 |
| Helper / muted | Inter | 12px | 400 |
| **Code / JSON / EDI** | **JetBrains Mono / ui-monospace** | 13px | 400 |

Rules:
- Use a **monospace** font for all EDI and JSON content (alignment matters).
- Line height: **1.5** for body, **1.4** for code.
- No more than **two** font families total (one sans, one mono).
- Avoid all-caps except tiny labels; use sentence case for buttons.

---

## 5.4 Rules & Regulations of Website Design

### Usability
- **One primary action per screen** — the upload/convert flow is the star.
- Immediate feedback: show a spinner within 100ms of any action.
- Never a dead end: every error tells the user what to do next.
- Preserve the user's file/selection after an error (don't reset the form).

### Accessibility (required, not optional)
- Full **keyboard navigation**; visible focus rings.
- Proper labels on all inputs; `aria-live` region for async results/errors.
- Dropzone must also work via a real `<input type="file">` (not drag-only).
- Color contrast **WCAG AA**; status uses icon + text, not color alone.

### Responsiveness
- Mobile-first; single column on small screens, two-column controls on desktop.
- Result panel scrolls internally (`overflow: auto`) — never break page layout
  with wide JSON.

### Performance
- Lazy-load the JSON viewer for large results.
- Stream/paginate very large outputs instead of freezing the tab.

### Trust & safety (healthcare-specific)
- Show a small note: **"Files are processed in memory and not stored."** (true in
  v1 — see `3-rules.md`).
- No third-party trackers/analytics that could see PHI.
- Clear the result from memory when a new file is uploaded.

### Consistency
- All colors/spacing/type come from the tokens above — **no ad-hoc hex values**
  in components.
- Reuse components; don't duplicate buttons/inputs with slightly different styles.
