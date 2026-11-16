/** Lectures et écritures de l'API, avec cache (TanStack Query). */

import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

import { api, ApiError, type S } from "./client";

export const keys = {
  me: ["me"] as const,
  catalog: ["catalog"] as const,
  home: ["home"] as const,
  collection: (id: number) => ["collection", id] as const,
  checklist: (seriesId: number, version: number) => ["checklist", seriesId, version] as const,
  card: (refId: number) => ["card", refId] as const,
  isolated: ["isolated"] as const,
  purchases: ["purchases"] as const,
  purchase: (id: number) => ["purchases", id] as const,
  sharing: ["sharing"] as const,
};

/** Checklist d'une série : [id, code, nom, indice de sous-série, indices d'équipes, drapeaux]. */
export type ChecklistRow = [number, string, string, number, number[], number];
export type Checklist = {
  series_id: number;
  version: number;
  groups: { id: number; name: string; kind: string }[];
  teams: string[];
  cards: ChecklistRow[];
  chase: Record<string, string>;
};

// ------------------------------------------------------------------ lectures

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: async () => {
      try {
        return await api<S["MeOut"]>("/me");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null; // visiteur
        throw error;
      }
    },
    staleTime: 60_000,
  });
}

export function useCatalogIndex() {
  return useQuery({ queryKey: keys.catalog, queryFn: () => api<S["CatalogOut"]>("/catalog"), staleTime: 600_000 });
}

export function useHome() {
  return useQuery({ queryKey: keys.home, queryFn: () => api<S["HomeOut"]>("/collections") });
}

export function useCollection(id: number) {
  return useQuery({
    queryKey: keys.collection(id),
    queryFn: () => api<S["CollectionDetailOut"]>(`/collections/${id}`),
  });
}

export function useChecklist(seriesId: number | null | undefined, version: number | null | undefined) {
  return useQuery({
    queryKey: keys.checklist(seriesId ?? 0, version ?? 0),
    queryFn: () => api<Checklist>(`/catalog/series/${seriesId}/cards`, { params: { v: version } }),
    enabled: Boolean(seriesId && version),
    staleTime: Infinity, // une version de checklist ne change jamais
    gcTime: 3_600_000,
  });
}

export function useCard(refId: number | null) {
  return useQuery({
    queryKey: keys.card(refId ?? 0),
    queryFn: () => api<S["CardOut"]>(`/cards/${refId}`),
    enabled: refId !== null,
  });
}

export function useIsolated() {
  return useQuery({ queryKey: keys.isolated, queryFn: () => api<S["IsolatedOut"][]>("/isolated") });
}

export function usePurchases(only: string) {
  return useQuery({
    queryKey: [...keys.purchases, "list", only],
    queryFn: () => api<S["PurchaseOut"][]>("/purchases", { params: { only, limit: 200 } }),
  });
}

export function usePurchase(id: number) {
  return useQuery({ queryKey: keys.purchase(id), queryFn: () => api<S["PurchaseOut"]>(`/purchases/${id}`) });
}

export function useSeriesList(params: Record<string, unknown>) {
  return useQuery({
    queryKey: ["series", params],
    queryFn: () => api<S["SeriesOut"][]>("/catalog/series", { params }),
    placeholderData: (previous) => previous,
  });
}

// ------------------------------------------------------- écritures courantes

/** Après une écriture, tout ce qui dépend de la possession est à relire. */
export function refreshOwnership(client: QueryClient): void {
  for (const key of [keys.home, keys.isolated, keys.purchases, ["collection"], ["card"], ["search"]]) {
    void client.invalidateQueries({ queryKey: key });
  }
}

export function useApiMutation<TVariables, TData = unknown>(
  run: (variables: TVariables) => Promise<TData>,
  after?: (client: QueryClient, data: TData, variables: TVariables) => void,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: (data, variables) => (after ? after(client, data, variables) : refreshOwnership(client)),
  });
}

// --------------------------------------------- cochage optimiste (T-08, CA-15)
//
// Une modification de carte s'affiche tout de suite. Les appels d'une même carte partent l'un
// après l'autre, toujours avec le dernier état voulu. En cas d'échec, l'affichage revient à l'état
// confirmé par le serveur et la modification attend dans `failed` : le bandeau « Réessayer » la rejoue.

export type CardPatch = { quantity?: number; wanted?: boolean; note?: string; photo_id?: string | null };
type Write = { collectionId: number | null; patch: CardPatch };
type Snapshot = { entry: number[] | undefined; card: S["CardOut"] | undefined };

const queued = new Map<number, Write>();
const inFlight = new Set<number>();
const snapshots = new Map<number, Snapshot>();
const failed = new Map<number, Write>();
const listeners = new Set<() => void>();
let failedCount = 0;

function notify(): void {
  failedCount = failed.size;
  listeners.forEach((listener) => listener());
}

function applyLocally(client: QueryClient, refId: number, { collectionId, patch }: Write): void {
  client.setQueryData<S["CardOut"]>(keys.card(refId), (card) => (card ? { ...card, ...patch } : card));
  if (collectionId === null) return;
  client.setQueryData<S["CollectionDetailOut"]>(keys.collection(collectionId), (collection) => {
    if (!collection) return collection;
    const [quantity, parallels, photo, wanted] = collection.cards[refId] ?? [0, 0, 0, 0];
    const entry = [
      patch.quantity ?? quantity,
      parallels,
      patch.photo_id === undefined ? photo : Number(Boolean(patch.photo_id)),
      patch.wanted === undefined ? wanted : Number(patch.wanted),
    ];
    return { ...collection, cards: { ...collection.cards, [refId]: entry } };
  });
}

function restore(client: QueryClient, refId: number, collectionId: number | null): void {
  const snapshot = snapshots.get(refId);
  if (!snapshot) return;
  client.setQueryData(keys.card(refId), snapshot.card);
  if (collectionId !== null) {
    client.setQueryData<S["CollectionDetailOut"]>(keys.collection(collectionId), (collection) => {
      if (!collection) return collection;
      const cards = { ...collection.cards };
      if (snapshot.entry) cards[refId] = snapshot.entry;
      else delete cards[refId];
      return { ...collection, cards };
    });
  }
}

async function flush(client: QueryClient, refId: number): Promise<void> {
  if (inFlight.has(refId)) return;
  const write = queued.get(refId);
  if (!write) return;
  queued.delete(refId);
  inFlight.add(refId);
  try {
    const card = await api<S["CardOut"]>(`/cards/${refId}`, { method: "PUT", body: write.patch });
    if (queued.has(refId)) {
      // D'autres appuis attendent : l'état confirmé devient le point de retour en cas d'échec.
      const live = card.parallels.filter((parallel) => !parallel.sold);
      const photo = Number(Boolean(card.photo_id) || live.some((parallel) => parallel.photo_id));
      snapshots.set(refId, { entry: [card.quantity, live.length, photo, Number(card.wanted)], card });
    } else {
      snapshots.delete(refId);
      client.setQueryData(keys.card(refId), card);
    }
    failed.delete(refId);
    void client.invalidateQueries({ queryKey: keys.home });
  } catch {
    const later = queued.get(refId);
    queued.delete(refId);
    restore(client, refId, write.collectionId); // retour arrière visible
    snapshots.delete(refId);
    failed.set(refId, { collectionId: write.collectionId, patch: { ...write.patch, ...later?.patch } });
  } finally {
    inFlight.delete(refId);
    notify();
    if (queued.has(refId)) void flush(client, refId);
  }
}

function writeCard(client: QueryClient, refId: number, write: Write): void {
  if (!snapshots.has(refId)) {
    const collection =
      write.collectionId === null
        ? undefined
        : client.getQueryData<S["CollectionDetailOut"]>(keys.collection(write.collectionId));
    snapshots.set(refId, { entry: collection?.cards[refId], card: client.getQueryData(keys.card(refId)) });
  }
  const pending = queued.get(refId);
  queued.set(refId, { collectionId: write.collectionId, patch: { ...pending?.patch, ...write.patch } });
  applyLocally(client, refId, write);
  void flush(client, refId);
}

/** Écrit l'état d'une carte, avec affichage immédiat. */
export function useCardWriter(collectionId: number | null) {
  const client = useQueryClient();
  return (refId: number, patch: CardPatch) => writeCard(client, refId, { collectionId, patch });
}

/** Modifications en échec et moyen de les rejouer (bandeau « Réessayer »). */
export function useFailedWrites() {
  const client = useQueryClient();
  const count = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => failedCount,
  );
  const retry = () => {
    const entries = [...failed.entries()];
    failed.clear();
    notify();
    for (const [refId, write] of entries) writeCard(client, refId, write);
  };
  return { count, retry };
}
