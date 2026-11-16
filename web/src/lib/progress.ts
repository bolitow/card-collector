/** Avancement d'une collection (RG-15), même règle que backend/app/rules/progress.py. */

export type Progress = { owned: number; total: number; percent: number; label: string };

export function progress(totalByKind: Record<string, number>, ownedByKind: Record<string, number>): Progress {
  const kinds = Object.keys(totalByKind).filter((kind) => totalByKind[kind] > 0);
  // Sur la base quand la collection mélange plusieurs types et qu'une carte de base est possédée.
  const onBase = kinds.length > 1 && (ownedByKind.base ?? 0) > 0;
  const sum = (counts: Record<string, number>) => Object.values(counts).reduce((a, b) => a + b, 0);
  const owned = onBase ? ownedByKind.base : sum(ownedByKind);
  const total = onBase ? totalByKind.base : sum(totalByKind);
  const percent = total ? Math.floor((owned * 100) / total) : 0; // 100 % seulement quand tout est possédé
  return { owned, total, percent, label: owned > 0 && percent < 1 ? "<1 %" : `${percent} %` };
}
