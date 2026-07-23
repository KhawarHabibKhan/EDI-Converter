import { NavLink } from "react-router-dom";

export interface HeaderStatus {
  kind: string;
  text: string;
}

/** Shared top bar: brand, page nav (Converter · FHIR), API status, theme toggle.
 *  Rendered by both routed pages so the header stays identical everywhere. */
export function Header({
  theme,
  onToggleTheme,
  status,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  status: HeaderStatus;
}) {
  return (
    <header className="bar glass">
      <div className="brand">
        <div className="mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round"><path d="M3 12h4l2 5 4-10 2 5h6" /></svg>
        </div>
        <div><h1>EDI Converter</h1><p>X12 · Healthcare EDI</p></div>
      </div>

      <nav className="nav" aria-label="Pages">
        <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          Converter
        </NavLink>
        <NavLink to="/fhir" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          FHIR Converter
        </NavLink>
      </nav>

      <div className="bar-right">
        <div className={`status ${status.kind}`}><span className="dot" /><span>{status.text}</span></div>
        <button className="icon-btn" onClick={onToggleTheme} aria-label="Toggle theme">
          {theme === "dark" ? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" /></svg>
          )}
        </button>
      </div>
    </header>
  );
}
