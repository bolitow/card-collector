/** Appels à l'API /api/v1. La session est un cookie HttpOnly : rien n'est stocké côté script. */

import type { components } from "./schema";

export type S = components["schemas"];

const BASE = "/api/v1";
let knownVersion: string | null = null;
let outdated = false;

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public details: Record<string, unknown> = {},
  ) {
    super(code);
  }
}

/** Vrai quand le serveur a été mis à jour depuis le chargement de la page (8.3). */
export function isOutdated(): boolean {
  return outdated;
}

type Options = { method?: string; body?: unknown; form?: FormData; params?: Record<string, unknown> };

export async function api<T = unknown>(path: string, options: Options = {}): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(options.params ?? {})) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  const url = `${BASE}${path}${query.size ? `?${query}` : ""}`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? (options.body !== undefined || options.form ? "POST" : "GET"),
      credentials: "same-origin",
      headers: options.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: options.form ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
    });
  } catch {
    throw new ApiError(0, "network");
  }
  const version = response.headers.get("X-App-Version");
  if (version) {
    if (knownVersion && knownVersion !== version) outdated = true;
    knownVersion ??= version;
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error ?? {};
    const { code = response.status === 422 ? "invalid" : "generic", message: _message, ...details } = error;
    throw new ApiError(response.status, code, details);
  }
  return data as T;
}

export function photoUrl(id: string, size: "thumb" | "medium" | "large", shareToken?: string | null): string {
  // Dans une vue publique, la photo passe par le point d'accès public, avec le lien secret éventuel.
  if (shareToken === undefined) return `${BASE}/photos/${id}/${size}`;
  return `${BASE}/public/photos/${id}/${size}${shareToken ? `?token=${encodeURIComponent(shareToken)}` : ""}`;
}
