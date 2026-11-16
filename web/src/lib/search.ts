/**
 * Recherche de cartes (F-09). Mêmes règles que backend/app/rules/search.py ; les deux
 * implémentations sont vérifiées par shared/search-vectors.json (CA-12).
 */

const EXACT = "=";

export type Term = { kind: "word" | "exact"; value: string };

/** Minuscules sans accents. */
export function fold(text: string): string {
  return text.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
}

function words(text: string): string[] {
  return fold(text).match(/[a-z0-9]+/g) ?? [];
}

/** Jetons d'une carte : mots (recherche par début de mot) et jetons exacts préfixés par « = ». */
export function cardTokens(code: string, name: string, group = "", teams: string[] = []): string[] {
  const segments = words(code);
  const exact = new Set<string>([segments.join(""), ...segments]);
  for (const segment of segments) {
    for (const run of segment.match(/\d+/g) ?? []) exact.add(String(Number(run))); // « 045 » = « 45 »
  }
  const found = new Set<string>(segments.filter((s) => !/^\d+$/.test(s)));
  for (const text of [name, group, ...teams]) {
    for (const word of words(text)) found.add(word);
    // « O'Neal » doit répondre à « oneal » comme à « neal ».
    for (const raw of fold(text).split(/\s+/)) {
      if (raw.includes("'") || raw.includes("’")) found.add(raw.replace(/[^a-z0-9]/g, ""));
    }
  }
  found.delete("");
  return [...found, ...[...exact].map((e) => EXACT + e)];
}

export function parseQuery(query: string): Term[] {
  const terms: Term[] = [];
  for (const raw of fold(query).split(/\s+/)) {
    const token = raw.replace(/[^a-z0-9]/g, "");
    if (!token) continue;
    if (/^\d+$/.test(token)) terms.push({ kind: "exact", value: String(Number(token)) });
    else if (/\d/.test(token)) terms.push({ kind: "exact", value: token });
    else terms.push({ kind: "word", value: token });
  }
  return terms;
}

/** Vrai si tous les termes correspondent : un mot par son début, un code ou un nombre à l'identique. */
export function matches(terms: Term[], tokens: string[]): boolean {
  return terms.every((term) =>
    term.kind === "exact"
      ? tokens.includes(EXACT + term.value)
      : tokens.some((t) => !t.startsWith(EXACT) && t.startsWith(term.value)),
  );
}
