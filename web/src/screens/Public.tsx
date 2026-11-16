import { useQuery } from "@tanstack/react-query";
import { Eye, Flame, Star } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, type S } from "@/api/client";
import { useMe } from "@/api/hooks";
import { t, tn } from "@/i18n";
import { formatCodeList } from "@/lib/codes";
import { cardTokens, matches, parseQuery } from "@/lib/search";
import { ErrorNote, Loading, Photo, SearchBox, useUniverses, Viewer } from "@/ui/parts";
import { Sheet } from "@/ui/sheet";
import { ReportSheet } from "./CardSheet";

type Profile = S["PublicProfileOut"];
type Collection = S["PublicCollectionOut"];
/** undefined : aperçu du propriétaire (photos privées) ; null : profil public ; texte : lien secret. */
type Access = string | null | undefined;

type Shown = { id: string; alt: string; photoId: string };

function Gallery(props: {
  items: { key: string; name: string; code: string; detail: string; chase?: boolean; photoIds: string[] }[];
  access: Access;
  onOpen: (shown: Shown) => void;
}) {
  return (
    <div className="gallery">
      {props.items.map((item) => (
        <figure key={item.key}>
          {item.photoIds.length > 0 ? (
            <button className="photo" onClick={() => props.onOpen({ id: item.key, alt: item.name, photoId: item.photoIds[0] })} aria-label={item.name}>
              <Photo id={item.photoIds[0]} size="medium" alt="" shareToken={props.access} className="" />
              {item.photoIds.length > 1 && <span className="badge">{tn("public.photos", item.photoIds.length)}</span>}
            </button>
          ) : (
            <div className="photo"><Photo id={null} alt="" className="" /></div>
          )}
          <figcaption>
            <strong>
              {item.chase && <Flame size={12} fill="currentColor" aria-label={t("card.wanted.editorial")} style={{ display: "inline", marginRight: 4 }} />}
              {item.name || `#${item.code}`}
            </strong>
            <span className="muted">
              {item.code && <span className="mono">#{item.code}</span>}
              {item.detail && ` · ${item.detail}`}
            </span>
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

/** F-43 : vue publique. Lecture seule, cartes détenues en photo, jamais de prix (RG-02). */
function PublicView(props: { profile: Profile; access: Access; pseudo?: string }) {
  const { profile, access } = props;
  const me = useMe();
  const universes = useUniverses();
  const [universe, setUniverse] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [shown, setShown] = useState<Shown | null>(null);
  const [reporting, setReporting] = useState<{ photoId?: string } | null>(null);
  const [comparing, setComparing] = useState<Collection | null>(null);

  const terms = useMemo(() => parseQuery(query), [query]);
  const collections = profile.collections
    .filter((c) => (universe ? c.universe_id === universe : true) && (selected ? c.id === selected : true))
    .map((c) => ({
      ...c,
      cards: terms.length ? c.cards.filter((card) => matches(terms, cardTokens(card.code, card.name, card.group, card.teams))) : c.cards,
    }));
  const singles = profile.singles.filter((s) => (universe ? s.universe_id === universe : true) && selected === null);
  const total = profile.collections.reduce((sum, c) => sum + c.cards.length, 0) + profile.singles.length;
  const perUniverse = new Map<number, number>();
  for (const c of profile.collections) perUniverse.set(c.universe_id, (perUniverse.get(c.universe_id) ?? 0) + c.cards.length);
  for (const s of profile.singles) if (s.universe_id) perUniverse.set(s.universe_id, (perUniverse.get(s.universe_id) ?? 0) + 1);
  const isOwner = me.data?.pseudo === profile.pseudo;

  return (
    <main className="screen wide bare stack loose">
      <div className="spread">
        <span className="chip"><Eye size={12} aria-hidden="true" />{t("public.readOnly")}</span>
        {access !== undefined && <button className="link small" onClick={() => setReporting({})}>{t("common.report")}</button>}
      </div>
      <div className="stack" style={{ gap: 6 }}>
        <h1 className="title">{props.pseudo ? t("public.of", { pseudo: props.pseudo }) : t("public.title")}</h1>
        <p className="muted">{t("public.lead")}</p>
      </div>

      {total === 0 && <p className="empty">{t("public.empty")}</p>}

      {perUniverse.size > 1 && (
        <div className="pills" role="group">
          <button className="pill" aria-pressed={universe === null} onClick={() => setUniverse(null)}>
            {t("catalog.any")}<span className="count">·{total}</span>
          </button>
          {universes.list.filter((u) => perUniverse.has(u.id)).map((u) => (
            <button key={u.id} className="pill" aria-pressed={universe === u.id} style={universes.style(u.id)} onClick={() => setUniverse(u.id)}>
              <span className="dot" />{u.name}<span className="count">·{perUniverse.get(u.id)}</span>
            </button>
          ))}
        </div>
      )}

      {singles.length > 0 && (
        <section>
          <h2 className="group-header" style={{ marginTop: 0 }}>
            <span>{t("public.singles")}</span>
            <span className="mono muted small">{singles.length}</span>
          </h2>
          <Gallery
            access={access}
            onOpen={setShown}
            items={singles.map((s, index) => ({ key: `s${index}`, name: s.name, code: s.code, detail: s.variant || s.series_name, photoIds: s.photo_ids }))}
          />
        </section>
      )}

      {profile.collections.length > 1 && (
        <div className="pills" role="group">
          {profile.collections.map((c) => (
            <button key={c.id} className="pill" aria-pressed={selected === c.id} onClick={() => setSelected(selected === c.id ? null : c.id)}>
              {c.short_name}<span className="count">·{c.cards.length}</span>
            </button>
          ))}
        </div>
      )}
      {profile.collections.length > 0 && <SearchBox value={query} onChange={setQuery} placeholder={t("collection.search")} />}

      {collections.map((collection) => (
        <section key={collection.id} style={universes.style(collection.universe_id)}>
          <h2 className="group-header" style={{ marginTop: 0 }}>
            <span className="cluster">
              <span className="dot" />
              {collection.name}
              {collection.priority_team && (
                <span className="chip"><Star size={11} fill="currentColor" aria-hidden="true" />{collection.priority_team}</span>
              )}
            </span>
            <span className="mono muted small">{collection.cards.length}</span>
          </h2>
          <Gallery
            access={access}
            onOpen={setShown}
            items={collection.cards.map((card) => ({
              key: `c${card.card_ref_id}`,
              name: card.name,
              code: card.code,
              detail: card.parallels.join(", "),
              chase: card.chase,
              photoIds: card.photo_ids,
            }))}
          />
          {collection.missing.length > 0 && (
            <details className="panel outline" style={{ marginTop: 12 }}>
              <summary style={{ cursor: "pointer", fontWeight: 600 }}>
                {t("public.missing")} <span className="mono muted">{collection.missing.length}</span>
              </summary>
              <p className="mono small" style={{ marginTop: 8, wordBreak: "break-word" }}>{formatCodeList(collection.missing.map((m) => m.code), true)}</p>
            </details>
          )}
          {/* Ajout : un collectionneur connecté compare cette collection à la sienne. */}
          {me.data && !isOwner && access === null && (
            <button className="button" style={{ marginTop: 12 }} onClick={() => setComparing(collection)}>{t("public.compare")}</button>
          )}
        </section>
      ))}

      {!me.data && !me.isPending && <Link to="/inscription" className="button primary big block">{t("public.join")}</Link>}

      {shown && (
        <>
          <Viewer id={shown.photoId} alt={shown.alt} shareToken={access} onClose={() => setShown(null)} />
          {access !== undefined && (
            <button className="button" style={{ position: "fixed", zIndex: 61, bottom: 20, left: "50%", translate: "-50% 0" }} onClick={() => { setReporting({ photoId: shown.photoId }); setShown(null); }}>
              {t("common.report")}
            </button>
          )}
        </>
      )}
      {reporting && <ReportSheet pseudo={profile.pseudo} photoId={reporting.photoId} onClose={() => setReporting(null)} />}
      {comparing && <CompareSheet pseudo={profile.pseudo} collection={comparing} onClose={() => setComparing(null)} />}
    </main>
  );
}

function CompareSheet({ pseudo, collection, onClose }: { pseudo: string; collection: Collection; onClose: () => void }) {
  const result = useQuery({
    queryKey: ["compare", pseudo, collection.id],
    queryFn: () => api<S["CompareOut"]>(`/public/compare/${pseudo}/${collection.id}`),
  });
  const list = (items: S["PublicMissingOut"][]) =>
    items.length ? <p className="mono small" style={{ wordBreak: "break-word" }}>{formatCodeList(items.map((i) => i.code), true)}</p> : <p className="small muted">{t("public.compare.none")}</p>;
  return (
    <Sheet title={collection.short_name} onClose={onClose}>
      {result.isPending && <Loading rows={2} />}
      {result.isError && <ErrorNote error={result.error} />}
      {result.data && (
        <div className="stack">
          <div className="panel stack">
            <strong>{t("public.compare.theyHave")} <span className="mono muted">{result.data.they_have_i_miss.length}</span></strong>
            {list(result.data.they_have_i_miss)}
          </div>
          <div className="panel stack">
            <strong>{t("public.compare.iHave")} <span className="mono muted">{result.data.i_have_they_miss.length}</span></strong>
            {collection.missing.length === 0 ? <p className="small muted">{t("public.compare.needMissing")}</p> : list(result.data.i_have_they_miss)}
          </div>
          {!result.data.following && <Link className="button block" to={`/catalogue/${collection.series_id}`}>{t("series.follow")}</Link>}
        </div>
      )}
    </Sheet>
  );
}

export function PublicProfile() {
  const { pseudo = "" } = useParams();
  const profile = useQuery({ queryKey: ["public", pseudo], queryFn: () => api<Profile>(`/public/profiles/${pseudo}`), retry: false });
  if (profile.isPending) return <div className="screen bare"><Loading /></div>;
  if (profile.isError) return <div className="screen bare"><ErrorNote error={profile.error} /></div>;
  return <PublicView profile={profile.data} access={null} pseudo={profile.data.pseudo} />;
}

/** F-42 : une seule collection, par lien secret. */
export function PublicLink() {
  const { token = "" } = useParams();
  const collection = useQuery({ queryKey: ["public-link", token], queryFn: () => api<Collection>(`/public/links/${token}`), retry: false });
  if (collection.isPending) return <div className="screen bare"><Loading /></div>;
  if (collection.isError) return <div className="screen bare"><ErrorNote error={collection.error} /></div>;
  return <PublicView profile={{ pseudo: "", avatar_photo_id: null, collections: [collection.data], singles: [] }} access={token} />;
}

/** F-44 « Aperçu » : ce que voient exactement les visiteurs. */
export function SharingPreview() {
  const preview = useQuery({ queryKey: ["sharing-preview"], queryFn: () => api<Profile>("/me/sharing/preview") });
  return (
    <>
      <div className="screen wide bare" style={{ paddingBottom: 0 }}>
        <div className="banner">
          <span>{t("sharing.preview.banner")}</span>
          <Link to="/profil/partage" className="link">{t("sharing.preview.quit")}</Link>
        </div>
      </div>
      {preview.isPending && <div className="screen"><Loading /></div>}
      {preview.isError && <div className="screen"><ErrorNote error={preview.error} /></div>}
      {preview.data && <PublicView profile={preview.data} access={undefined} />}
    </>
  );
}
