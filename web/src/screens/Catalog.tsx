import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight, Flame } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, type S } from "@/api/client";
import { refreshOwnership, useApiMutation, useCatalogIndex, useMe, useSeriesList } from "@/api/hooks";
import { t, tn, type Key } from "@/i18n";
import { shortDate } from "@/lib/format";
import { apiErrorText, ErrorNote, Field, Loading, SearchBox, useUniverses } from "@/ui/parts";
import { Sheet, useSheetParam } from "@/ui/sheet";
import { toast } from "@/ui/toast";

/** Bandeau des pages publiques pour un visiteur sans compte. */
export function VisitorBar() {
  const me = useMe();
  if (me.data || me.isPending) return null;
  return (
    <header className="spread" style={{ maxWidth: 1080, margin: "0 auto", padding: "14px 16px 0" }}>
      <Link to="/" className="heading" style={{ textDecoration: "none" }}>{t("app.name")}</Link>
      <Link to="/connexion" className="button">{t("nav.signIn")}</Link>
    </header>
  );
}

/** F-32 : parcourir le catalogue par univers, éditeur et saison. Accessible sans compte. */
export function Catalog() {
  const me = useMe();
  const index = useCatalogIndex();
  const universes = useUniverses();
  const [params] = useSearchParams();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [universe, setUniverse] = useState<number | null>(null);
  const [publisher, setPublisher] = useState("");
  const [season, setSeason] = useState("");
  const [panel, openPanel, closePanel] = useSheetParam("panneau");
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 200);
    return () => window.clearTimeout(timer);
  }, [query]);
  // Lien « Demander l'ajout » depuis les cartes isolées : le nom de la série est repris.
  const requested = params.get("demande");
  useEffect(() => {
    if (requested && me.data && panel !== "demande") openPanel("demande");
  }, [requested, Boolean(me.data)]); // eslint-disable-line react-hooks/exhaustive-deps

  const list = useSeriesList({ q: debounced, universe, publisher, season });

  return (
    <>
      <VisitorBar />
      <main className="screen stack loose">
        <h1 className="title">{t("catalog.title")}</h1>
        <SearchBox value={query} onChange={setQuery} placeholder={t("catalog.search")} />

        <div className="pills" role="group">
          <button className="pill" aria-pressed={universe === null} onClick={() => setUniverse(null)}>{t("catalog.any")}</button>
          {universes.list.map((u) => (
            <button key={u.id} className="pill" aria-pressed={universe === u.id} style={universes.style(u.id)} onClick={() => setUniverse(universe === u.id ? null : u.id)}>
              <span className="dot" />
              {u.name}
            </button>
          ))}
        </div>
        <div className="cluster">
          <select className="pill" aria-label={t("catalog.publisher")} value={publisher} onChange={(e) => setPublisher(e.target.value)}>
            <option value="">{t("catalog.publisher")}</option>
            {index.data?.publishers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <select className="pill" aria-label={t("catalog.season")} value={season} onChange={(e) => setSeason(e.target.value)}>
            <option value="">{t("catalog.season")}</option>
            {index.data?.seasons.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>

        {list.isPending && <Loading />}
        {list.isError && <ErrorNote error={list.error} retry={() => list.refetch()} />}
        {list.data?.length === 0 && <p className="empty">{t("catalog.empty")}</p>}
        <div>
          {list.data?.map((series) => (
            <Link key={series.id} to={`/catalogue/${series.id}`} className="row collection-row" style={universes.style(series.universe_id)}>
              <div className="spread">
                <span className="name">{series.short_name}</span>
                {series.followed ? (
                  <span className="chip"><Check size={12} aria-hidden="true" />{t("catalog.followed")}</span>
                ) : (
                  <ChevronRight size={16} aria-hidden="true" />
                )}
              </div>
              <div className="meta">
                {[universes.name(series.universe_id), series.publisher, series.season, tn("catalog.cards", series.card_count)].filter(Boolean).join(" · ")}
              </div>
            </Link>
          ))}
        </div>

        {me.data && (
          <section className="panel outline stack">
            <p className="small">{t("catalog.request.lead")}</p>
            <button className="button block" onClick={() => openPanel("demande")}>{t("catalog.request")}</button>
            <button className="link small" onClick={() => openPanel("personnelle")}>{t("catalog.personal")}</button>
          </section>
        )}
        {me.data && <Requests />}
      </main>
      {panel === "demande" && <RequestSheet initialName={requested ?? ""} onClose={closePanel} />}
      {panel === "personnelle" && <PersonalSheet onClose={closePanel} />}
    </>
  );
}

function useRequests() {
  return useQuery({ queryKey: ["requests"], queryFn: () => api<S["SeriesRequestOut"][]>("/catalog/requests") });
}

/** Demandes en cours. Ajout : « Moi aussi » évite les doublons et sert à prioriser. */
function Requests() {
  const requests = useRequests();
  const client = useQueryClient();
  const vote = useApiMutation((id: number) => api(`/catalog/requests/${id}/vote`, { method: "POST" }), () => void client.invalidateQueries({ queryKey: ["requests"] }));
  if (!requests.data?.length) return null;
  return (
    <section className="stack">
      <h2 className="heading">{t("catalog.request.list")}</h2>
      <div>
        {requests.data.map((request) => (
          <div key={request.id} className="row">
            <span className="grow">
              <span className="name" style={{ display: "block" }}>{request.name}</span>
              <span className="meta" style={{ display: "block" }}>
                {t(`catalog.request.status.${request.status}` as Key)} · {tn("catalog.request.votes", request.votes)}
              </span>
              {request.admin_reply && <span className="small" style={{ display: "block" }}>{request.admin_reply}</span>}
            </span>
            {request.series_id && request.status === "published" ? (
              <Link className="button" to={`/catalogue/${request.series_id}`}>{t("common.see")}</Link>
            ) : request.mine || request.voted ? (
              <span className="chip">{t("catalog.request.voted")}</span>
            ) : (
              <button className="button" disabled={vote.isPending} onClick={() => vote.mutate(request.id)}>{t("catalog.request.metoo")}</button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

/** F-34 : demander l'ajout d'une série. */
function RequestSheet({ initialName, onClose }: { initialName: string; onClose: () => void }) {
  const client = useQueryClient();
  const [name, setName] = useState(initialName);
  const [url, setUrl] = useState("");
  const send = useApiMutation(
    () => api("/catalog/requests", { body: { name, url } }),
    () => {
      void client.invalidateQueries({ queryKey: ["requests"] });
      toast(t("catalog.request.sent"));
      onClose();
    },
  );
  return (
    <Sheet title={t("catalog.request")} onClose={onClose}>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); send.mutate(undefined); }}>
        <Field label={t("catalog.request.name")}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("catalog.request.name.placeholder")} required minLength={3} autoFocus />
        </Field>
        <Field label={`${t("catalog.request.url")} (${t("common.optional")})`}>
          <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
        </Field>
        {send.isError && <p className="error-text" role="alert">{apiErrorText(send.error)}</p>}
        <button className="button primary big block" disabled={send.isPending}>{t("catalog.request.submit")}</button>
      </form>
    </Sheet>
  );
}

/** F-35 : collection personnelle à partir d'une liste de codes, en attendant la série. */
function PersonalSheet({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const universes = useUniverses();
  const [name, setName] = useState("");
  const [codes, setCodes] = useState("");
  const [universeId, setUniverseId] = useState<number | null>(null);
  const create = useApiMutation(
    () => api<S["CollectionOut"]>("/collections/personal", { body: { name, codes, universe_id: universeId } }),
    (client, created) => {
      refreshOwnership(client);
      navigate(`/collections/${created.id}`, { replace: true });
    },
  );
  return (
    <Sheet title={t("catalog.personal")} onClose={onClose}>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); create.mutate(undefined); }}>
        <Field label={t("catalog.personal.name")}>
          <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        </Field>
        <div className="cluster">
          {universes.list.map((u) => (
            <button type="button" key={u.id} className="pill" aria-pressed={universeId === u.id} onClick={() => setUniverseId(universeId === u.id ? null : u.id)}>
              {u.name}
            </button>
          ))}
        </div>
        <Field label={t("catalog.personal.codes")} hint={t("import.text")}>
          <textarea value={codes} onChange={(e) => setCodes(e.target.value)} rows={5} placeholder={t("import.placeholder")} />
        </Field>
        {create.isError && <p className="error-text" role="alert">{apiErrorText(create.error)}</p>}
        <button className="button primary big block" disabled={create.isPending}>{t("catalog.personal.submit")}</button>
      </form>
    </Sheet>
  );
}

/** F-33 : fiche d'une série. */
export function SeriesPage() {
  const id = Number(useParams().id);
  const me = useMe();
  const navigate = useNavigate();
  const universes = useUniverses();
  const series = useQuery({ queryKey: ["series", id], queryFn: () => api<S["SeriesDetailOut"]>(`/catalog/series/${id}`) });
  const follow = useApiMutation(
    () => api<S["CollectionOut"]>("/collections", { body: { series_id: id } }),
    (client, collection) => {
      refreshOwnership(client);
      void client.invalidateQueries({ queryKey: ["series"] });
      navigate(`/collections/${collection.id}`);
    },
  );

  if (series.isPending) return <div className="screen"><Loading /></div>;
  if (series.isError) return <div className="screen"><ErrorNote error={series.error} /></div>;
  const data = series.data;
  const kinds = ["base", "insert", "special", "relic", "auto"].filter((kind) => data.counts[kind]);

  return (
    <>
      <VisitorBar />
      <main className="screen stack loose" style={universes.style(data.universe_id)}>
        <Link to="/catalogue" className="back">
          <ChevronLeft size={16} aria-hidden="true" />
          {t("catalog.title")}
        </Link>
        <div className="stack" style={{ gap: 6 }}>
          <h1 className="title medium">{data.name}</h1>
          <p className="small muted cluster">
            <span className="dot" />
            {[universes.name(data.universe_id), data.publisher, data.season].filter(Boolean).join(" · ")}
          </p>
          {data.release_date && <p className="small muted">{t("series.released", { date: shortDate(data.release_date) })}</p>}
        </div>

        {data.collection_id ? (
          <Link className="button dark big block" to={`/collections/${data.collection_id}`}>{t("series.open")}</Link>
        ) : me.data ? (
          <button className="button primary big block" disabled={follow.isPending} onClick={() => follow.mutate(undefined)}>{t("series.follow")}</button>
        ) : (
          <Link className="button primary big block" to={`/inscription?suite=${encodeURIComponent(`/catalogue/${id}`)}`}>{t("series.signInToFollow")}</Link>
        )}
        {follow.isError && <p className="error-text" role="alert">{apiErrorText(follow.error)}</p>}

        <div className="tiles" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(96px, 1fr))" }}>
          <div className="stat"><strong>{data.card_count}</strong>{t("series.total")}</div>
          {kinds.map((kind) => (
            <div key={kind} className="stat"><strong>{data.counts[kind]}</strong>{t(`collection.kind.${kind}` as Key)}</div>
          ))}
        </div>

        {data.chase.length > 0 && (
          <section className="stack">
            <h2 className="heading">{t("series.chase")}</h2>
            <div>
              {data.chase.map((card) => (
                <div key={card.card_ref_id} className="row">
                  <Flame size={16} fill="currentColor" aria-hidden="true" />
                  <span className="grow">
                    <span className="name" style={{ display: "block" }}>{card.name}</span>
                    <span className="meta" style={{ display: "block", whiteSpace: "normal" }}>
                      <span className="mono">#{card.code}</span>{card.reason && ` · ${card.reason}`}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="stack">
          <h2 className="heading">{t("series.groups")}</h2>
          <div className="table">
            {data.groups.map((group) => (
              <div key={group.name}>
                <strong>{group.name}</strong>
                <span className="small muted">{t(`collection.kind.${group.kind}` as Key)}</span>
                <span className="mono">{group.card_count}</span>
              </div>
            ))}
          </div>
        </section>

        {data.source && (
          <p className="small muted">
            {t("series.source", { source: data.source })}
            {data.source_date && `, ${t("series.sourceDate", { date: shortDate(data.source_date) })}`}
          </p>
        )}
      </main>
    </>
  );
}
