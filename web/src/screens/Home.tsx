import { ChevronDown, ChevronRight, Plus, Star } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { S } from "@/api/client";
import { useHome } from "@/api/hooks";
import { t, tn } from "@/i18n";
import { ErrorNote, Loading, useUniverses } from "@/ui/parts";

type Collection = S["CollectionOut"];

/** Choix mémorisé sur l'appareil (F-04 : groupe « Pas commencées » repliable). */
function useStoredFlag(key: string, initial: boolean): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(() => {
    try {
      return (localStorage.getItem(key) ?? String(initial)) === "true";
    } catch {
      return initial;
    }
  });
  return [
    value,
    (next) => {
      setValue(next);
      try {
        localStorage.setItem(key, String(next));
      } catch {
        /* stockage indisponible : le choix vaut pour cette visite */
      }
    },
  ];
}

function CollectionRow({ collection }: { collection: Collection }) {
  const universes = useUniverses();
  // F-05 : « univers · ★ équipe prioritaire · marque · saison ».
  const meta = [universes.name(collection.universe_id), collection.publisher, collection.season].filter(Boolean);
  return (
    <Link to={`/collections/${collection.id}`} className="row collection-row" style={universes.style(collection.universe_id)}>
      <div className="spread">
        <span className="name">{collection.short_name}</span>
        <span className="percent" aria-label={t("collection.figure", { label: collection.label, owned: collection.owned, total: collection.total })}>
          {collection.label}
        </span>
      </div>
      <div className="meta">
        {meta[0]}
        {collection.priority_team && (
          <>
            {" · "}
            <Star size={10} fill="currentColor" aria-hidden="true" /> {collection.priority_team}
          </>
        )}
        {meta.slice(1).map((part) => ` · ${part}`)}
      </div>
      <div className="bar" aria-hidden="true">
        <span style={{ width: `${collection.percent}%` }} />
      </div>
    </Link>
  );
}

export function Home() {
  const home = useHome();
  const universes = useUniverses();
  const [universe, setUniverse] = useState<number | null>(null);
  const [showIdle, setShowIdle] = useStoredFlag("home.notStarted", true);

  if (home.isPending) return <div className="screen"><Loading /></div>;
  if (home.isError) return <div className="screen"><ErrorNote error={home.error} retry={() => home.refetch()} /></div>;

  const all = home.data.collections;
  if (all.length === 0 && home.data.isolated_cards === 0) {
    // Premier lancement (F-06).
    return (
      <main className="screen stack loose">
        <h1 className="title">{t("home.welcome.title")}</h1>
        <p>{t("home.welcome.text")}</p>
        <Link to="/catalogue" className="button primary big block">
          {t("home.welcome.cta")}
        </Link>
      </main>
    );
  }

  const counts = new Map<number, number>();
  for (const collection of all) {
    if (collection.universe_id) counts.set(collection.universe_id, (counts.get(collection.universe_id) ?? 0) + 1);
  }
  const shown = universe ? all.filter((c) => c.universe_id === universe) : all;
  const started = shown.filter((c) => c.owned > 0);
  const idle = shown.filter((c) => c.owned === 0);

  return (
    <main className="screen stack loose">
      <h1 className="title">{t("home.title")}</h1>

      <div className="pills" role="group" aria-label={t("home.title")}>
        <button className="pill" aria-pressed={universe === null} onClick={() => setUniverse(null)}>
          {t("common.all")}
          <span className="count">·{all.length}</span>
        </button>
        {universes.list
          .filter((u) => counts.has(u.id))
          .map((u) => (
            <button key={u.id} className="pill" aria-pressed={universe === u.id} onClick={() => setUniverse(u.id)} style={universes.style(u.id)}>
              <span className="dot" />
              {u.name}
              <span className="count">·{counts.get(u.id)}</span>
            </button>
          ))}
      </div>

      {started.length > 0 && (
        <section aria-labelledby="started">
          <h2 id="started" className="group-header" style={{ marginTop: 0 }}>
            <span>
              {t("home.inProgress")} <span className="mono muted">{started.length}</span>
            </span>
          </h2>
          {started.map((collection) => (
            <CollectionRow key={collection.id} collection={collection} />
          ))}
        </section>
      )}

      {idle.length > 0 && (
        <section>
          <button className="group-header" style={{ marginTop: 0, width: "100%" }} aria-expanded={showIdle} onClick={() => setShowIdle(!showIdle)}>
            <span>
              {t("home.notStarted")} <span className="mono muted">{idle.length}</span>
            </span>
            {showIdle ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>
          {showIdle && idle.map((collection) => <CollectionRow key={collection.id} collection={collection} />)}
        </section>
      )}

      <div>
        {home.data.isolated_cards > 0 && (
          <Link to="/collections/isolees" className="row">
            <div className="grow">
              <div className="name">{t("home.isolated")}</div>
              <div className="meta">
                {tn("home.isolated.meta", home.data.isolated_cards, { series: home.data.isolated_series })}
              </div>
            </div>
            <ChevronRight size={18} aria-hidden="true" />
          </Link>
        )}
        <Link to="/catalogue" className="button block" style={{ marginTop: 10 }}>
          <Plus size={16} aria-hidden="true" />
          {t("home.add")}
        </Link>
      </div>
    </main>
  );
}
