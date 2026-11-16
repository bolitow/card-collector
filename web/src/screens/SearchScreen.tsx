import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, type S } from "@/api/client";
import { t } from "@/i18n";
import { ErrorNote, Loading, Photo, SearchBox } from "@/ui/parts";
import { useSheetParam } from "@/ui/sheet";

/** F-25, F-26 : recherche sur toutes les collections, les achats hors collection, et le catalogue. */
export function SearchScreen() {
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const scope = params.get("onglet") === "catalogue" ? "catalog" : "mine";
  const only = params.get("vue") ?? "all";
  const [, openCard] = useSheetParam("carte");

  // La requête vit dans l'adresse : elle est conservée au retour d'une fiche (F-26).
  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next, { replace: true });
  };

  const [debounced, setDebounced] = useState(query);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 180);
    return () => window.clearTimeout(timer);
  }, [query]);

  const results = useQuery({
    queryKey: ["search", scope, only, debounced],
    queryFn: () => api<S["SearchOut"]>("/search", { params: { q: debounced, scope, only } }),
    enabled: debounced.trim().length > 0,
    placeholderData: (previous) => previous,
  });
  const data = debounced.trim() ? results.data : undefined;
  const counts = data?.counts ?? {};

  return (
    <main className="screen stack loose">
      <h1 className="title">{t("search.title")}</h1>
      <SearchBox value={query} onChange={(value) => update({ q: value })} placeholder={t("search.placeholder")} autoFocus />

      <div className="segmented" role="tablist">
        <button role="tab" aria-selected={scope === "mine"} aria-pressed={scope === "mine"} onClick={() => update({ onglet: "" })}>
          {t("search.tab.mine")}
        </button>
        <button role="tab" aria-selected={scope === "catalog"} aria-pressed={scope === "catalog"} onClick={() => update({ onglet: "catalogue" })}>
          {t("search.tab.catalog")}
        </button>
      </div>

      {scope === "mine" && data && (
        <div className="pills" role="group">
          {[
            { key: "all", label: t("common.all") },
            { key: "owned", label: t("search.filter.owned") },
            { key: "missing", label: t("search.filter.missing") },
          ].map((filter) => (
            <button key={filter.key} className="pill" aria-pressed={only === filter.key} onClick={() => update({ vue: filter.key === "all" ? "" : filter.key })}>
              {filter.label}
              <span className="count">·{counts[filter.key] ?? 0}</span>
            </button>
          ))}
        </div>
      )}

      {!debounced.trim() && <p className="empty">{t("search.start")}</p>}
      {results.isPending && debounced.trim() && <Loading />}
      {results.isError && <ErrorNote error={results.error} retry={() => results.refetch()} />}
      {data && data.results.length === 0 && <p className="empty">{t("search.empty")}</p>}

      <div aria-live="polite">
        {data?.results.map((result) => {
          const content = (
            <>
              <Photo id={result.photo_id} alt="" />
              <span className="grow">
                <span className="name" style={{ display: "block" }}>{result.name || `#${result.code}`}</span>
                <span className="meta" style={{ display: "block" }}>
                  {result.code && <span className="mono">#{result.code}</span>}
                  {result.detail && ` · ${result.detail}`}
                </span>
                <span className="meta" style={{ display: "block" }}>{result.series_name}</span>
              </span>
              {result.kind === "purchase" ? (
                <span className="chip">{t("search.purchase")}</span>
              ) : scope === "mine" ? (
                <span className={`chip ${result.owned ? "owned" : "outline"}`}>{result.owned ? t("search.owned") : t("search.missing")}</span>
              ) : null}
            </>
          );
          return result.kind === "purchase" ? (
            <Link key={`p${result.purchase_id}`} to={`/achats/${result.purchase_id}`} className="row">
              {content}
            </Link>
          ) : (
            // Toucher une carte ouvre sa fiche : on peut la cocher sans quitter la recherche.
            <button key={`c${result.card_ref_id}`} className="row" onClick={() => openCard(String(result.card_ref_id))}>
              {content}
            </button>
          );
        })}
      </div>
      {data?.truncated && <p className="note">{t("search.truncated")}</p>}
    </main>
  );
}
