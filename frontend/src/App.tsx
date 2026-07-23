import { Route, Routes } from "react-router-dom";
import ConverterPage from "./pages/ConverterPage";
import FhirPage from "./pages/FhirPage";

/** App shell: the shared aurora backdrop + the routed pages.
 *  "/"      → Converter (v1: JSON / XML / CSV / validate)
 *  "/fhir"  → FHIR Converter (v2: EDI/JSON/XML → FHIR R4 Bundle) */
export default function App() {
  return (
    <>
      <div className="aurora" aria-hidden="true"><span className="a" /><span className="b" /><span className="c" /></div>
      <Routes>
        <Route path="/" element={<ConverterPage />} />
        <Route path="/fhir" element={<FhirPage />} />
      </Routes>
    </>
  );
}
