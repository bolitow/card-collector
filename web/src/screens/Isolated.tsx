import { ChevronLeft } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import { useApiMutation, useIsolated } from "@/api/hooks";
import { t, tn } from "@/i18n";
import { ErrorNote, Loading, Photo, useUniverses } from "@/ui/parts";
import { useSheetParam } from "@/ui/sheet";

/** F-27 : galerie des cartes isolées par univers, et séries que l'on peut suivre en entier. */
export function Isolated() {
  const query = useIsolated();
  const universes = useUniverses();
  const [universe, setUniverse] = useState<number | null>(null);
  const [, openCard] = useSheetParam("carte");
  const follow = useApiMutation((seriesId: number) => api("/collections", { body: { series_id: seriesId } }));

  if (query.isPending) return <div className="screen"><Loading /></div>;
  if (query.isError) return <div className="screen"><ErrorNote error={query.error} retry={() => query.refetch()} /></div>;
  const items = query.data;
  const counts = new Map<number, number>();
  for (const item of items) if (item.universe_id) counts.set(item.universe_id, (counts.get(item.universe_id) ?? 0) + 1);
  const shown = universe ? items.filter((item) => item.universe_id === universe) : items;
  const groups = universes.list.filter((u) => shown.some((item) => item.universe_id === u.id));
  const others = shown.filter((item) => !item.universe_id);

  // Séries concernées : « Suivre » si la série est au catalogue, sinon « Demander l'ajout ».
  const series = new Map<string, { id: number | null; canFollow: boolean; count: number }>();
  for (const item of items) {
    const entry = series.get(item.series_name) ?? { id: item.series_id ?? null, canFollow: item.can_follow, count: 0 };
    entry.count++;
    series.set(item.series_name, entry);
  }

  const gallery = (list: typeof items) => (
    <div className="gallery">
      {list.map((item) => {
        const body = (
          <figure>
            <div className="photo">
              <Photo id={item.photo_id} size="medium" alt="" className="" />
            </div>
            <figcaption>
              <strong>{item.name || `#${item.code}`}</strong>
              <span className="muted">
                {item.code && <span className="mono">#{item.code}</span>}
                {item.variant && ` · ${item.variant}`}
              </span>
              <span className="muted" style={{ display: "block" }}>{item.series_name}</span>
            </figcaption>
          </figure>
        );
        return item.purchase_id ? (
          <Link key={`p${item.purchase_id}`} to={`/achats/${item.purchase_id}`} style={{ textDecoration: "none" }}>
            {body}
          </Link>
        ) : (
          <button key={`c${item.card_ref_id}`} style={{ textAlign: "left" }} onClick={() => openCard(String(item.card_ref_id))}>
            {body}
          </button>
        );
      })}
    </div>
  );

  return (
    <main className="screen wide stack loose">
      <Link to="/collections" className="back">
        <ChevronLeft size={16} aria-hidden="true" />
        {t("nav.collections")}
      </Link>
      <div className="stack" style={{ gap: 6 }}>
        <h1 className="title">{t("isolated.title")}</h1>
        <p className="muted">{items.length ? tn("isolated.lead", items.length) : t("isolated.empty")}</p>
      </div>

      {items.length > 0 && (
        <div className="pills" role="group">
          <button className="pill" aria-pressed={universe === null} onClick={() => setUniverse(null)}>
            {t("common.all")}
            <span className="count">·{items.length}</span>
          </button>
          {universes.list.filter((u) => counts.has(u.id)).map((u) => (
            <button key={u.id} className="pill" aria-pressed={universe === u.id} style={universes.style(u.id)} onClick={() => setUniverse(u.id)}>
              <span className="dot" />
              {u.name}
              <span className="count">·{counts.get(u.id)}</span>
            </button>
          ))}
        </div>
      )}

      {groups.map((u) => {
        const list = shown.filter((item) => item.universe_id === u.id);
        return (
          <section key={u.id} style={universes.style(u.id)}>
            <h2 className="group-header" style={{ marginTop: 0 }}>
              <span className="cluster"><span className="dot" />{u.name}</span>
              <span className="mono muted small">{list.length}</span>
            </h2>
            {gallery(list)}
          </section>
        );
      })}
      {others.length > 0 && gallery(others)}

      {series.size > 0 && (
        <section className="stack">
          <h2 className="heading">{t("isolated.followAll")}</h2>
          <div>
            {[...series.entries()].map(([name, entry]) => (
              <div key={name} className="row">
                <span className="grow">
                  <span className="name" style={{ display: "block" }}>{name}</span>
                  <span className="meta">{tn("purchases.count", entry.count)}</span>
                </span>
                {entry.canFollow && entry.id ? (
                  <button className="button dark" disabled={follow.isPending} onClick={() => follow.mutate(entry.id!)}>
                    {t("isolated.follow")}
                  </button>
                ) : (
                  <Link className="button" to={`/catalogue?demande=${encodeURIComponent(name)}`}>
                    {t("isolated.request")}
                  </Link>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
