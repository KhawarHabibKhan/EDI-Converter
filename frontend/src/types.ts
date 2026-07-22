// Shared frontend types. Kept in sync with the backend response shape.

export type TransactionType =
  | "auto"
  | "837P"
  | "837I"
  | "835"
  | "834"
  | "271"
  | "277";

export type OutputFormat = "json" | "csv" | "validation";

export interface ConversionResult {
  transaction_type: string;
  file_name: string;
  data: unknown;
  issues: unknown[];
}
