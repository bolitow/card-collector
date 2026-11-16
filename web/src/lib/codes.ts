/** Codes de cartes côté interface : tri naturel et listes à copier (RG-13, F-12). */

export function compareCodes(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
}

/**
 * Liste de codes à copier. Le format compact regroupe les numéros qui se suivent
 * (« 1-12, 15, 18-20 ») ; l'import de liste (F-37) sait le relire.
 */
export function formatCodeList(codes: string[], compact = false): string {
  if (!compact) return [...codes].sort(compareCodes).join(", ");

  const byWidth = new Map<number, number[]>();
  for (const code of codes) {
    if (!/^\d+$/.test(code)) continue;
    const width = code.startsWith("0") ? code.length : 0; // zéros de tête conservés
    byWidth.set(width, [...(byWidth.get(width) ?? []), Number(code)]);
  }
  const runs: { lo: number; hi: number; width: number }[] = [];
  for (const [width, values] of byWidth) {
    const ordered = [...new Set(values)].sort((a, b) => a - b);
    let lo = ordered[0];
    ordered.forEach((value, index) => {
      if (ordered[index + 1] !== value + 1) {
        runs.push({ lo, hi: value, width });
        lo = ordered[index + 1];
      }
    });
  }
  const write = (value: number, width: number) => String(value).padStart(width, "0");
  const numeric = runs
    .sort((a, b) => a.lo - b.lo || a.width - b.width)
    .map((r) => (r.lo === r.hi ? write(r.lo, r.width) : `${write(r.lo, r.width)}-${write(r.hi, r.width)}`));
  const others = codes.filter((c) => !/^\d+$/.test(c)).sort(compareCodes);
  return [...numeric, ...others].join(", ");
}
