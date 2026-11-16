import { fr, type Messages } from "./fr";

/** Langues disponibles. Ajouter une langue : un fichier de même forme que fr.ts, puis une entrée ici. */
const catalogs: Record<string, Messages> = { fr };

let locale = "fr";
let messages: Messages = fr;

export type Key = keyof Messages;
type PluralBase = { [K in Key]: K extends `${infer Base}.other` ? Base : never }[Key];
type Vars = Record<string, string | number>;

export function setLocale(next: string): void {
  locale = next in catalogs ? next : "fr";
  messages = catalogs[locale];
  document.documentElement.lang = locale;
}

export function getLocale(): string {
  return locale;
}

function fill(text: string, vars?: Vars): string {
  return vars ? text.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? "")) : text;
}

export function t(key: Key, vars?: Vars): string {
  return fill(messages[key], vars);
}

/** Texte au singulier ou au pluriel selon `count` (clés « base.one » / « base.other »). */
export function tn(base: PluralBase, count: number, vars?: Vars): string {
  const form = new Intl.PluralRules(locale).select(count) === "one" ? "one" : "other";
  const key = `${base}.${form}` as Key;
  return fill(messages[key in messages ? key : (`${base}.other` as Key)], { count, ...vars });
}

/** Message d'erreur pour un code renvoyé par l'API ; générique si le code est inconnu. */
export function errorText(code: string): string {
  const key = `error.${code}` as Key;
  return key in messages ? messages[key] : messages["error.generic"];
}
