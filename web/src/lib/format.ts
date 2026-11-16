import { getLocale } from "@/i18n";

/** RG-22 : montants dans la devise de l'utilisateur, dates selon la langue (JJ/MM/AA en français). */

export function money(value: string | number | null | undefined, currency = "EUR"): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = Number(value);
  return new Intl.NumberFormat(getLocale(), {
    style: "currency",
    currency,
    maximumFractionDigits: Number.isInteger(amount) ? 0 : 2,
  }).format(amount);
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(getLocale(), { day: "2-digit", month: "2-digit", year: "2-digit" }).format(
    new Date(iso),
  );
}

export function today(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

export function fileSize(bytes: number): string {
  return bytes > 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} Mo` : `${Math.max(1, Math.round(bytes / 1000))} Ko`;
}
