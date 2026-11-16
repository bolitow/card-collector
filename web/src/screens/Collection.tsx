import { ChevronLeft, Download, Flame, MoreHorizontal, Plus, Star } from "lucide-react";
import { memo, type MouseEvent, type PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, type S } from "@/api/client";
import { type Checklist, keys, refreshOwnership, useApiMutation, useCardWriter, useChecklist, useCollection } from "@/api/hooks";
import { t, tn, type Key } from "@/i18n";
import { compareCodes, formatCodeList } from "@/lib/codes";
import { progress } from "@/lib/progress";
import { cardTokens, matches, parseQuery } from "@/lib/search";
import { apiErrorText, Confirm, ErrorNote, Field, Loading, SearchBox, useUniverses } from "@/ui/parts";
import { Sheet, useSheetParam } from "@/ui/sheet";
import { toast } from "@/ui/toast";

type Card = { id: number; code: string; name: string; group: number; teams: number[]; rookie: boolean; chase: boolean };
type Entries = Record<string, number[]>;

const ROW_HEIGHT = 72; // hauteur d'une case + espacement, pour réserver la place des sous-séries non montées
const SLICE_ROWS = 12; // rangées par tranche
const LONG_PRESS_MS = 500;

/** État d'écran porté par l'adresse : un rechargement ne perd pas le contexte (F-03). */
function useUrlState(name: string, fallback: string): [string, (value: string) => void] {
  const [params, setParams] = useSearchParams();
  const value = params.get(name) ?? fallback;
  const set = (next: string) => {
    const search = new URLSearchParams(params);
    if (next === fallback) search.delete(name);
    else search.set(name, next);
    setParams(search, { replace: true });
  };
  return [value, set];
}

function isOwned(entry: number[] | undefined): boolean {
  return Boolean(entry && (entry[0] > 0 || entry[1] > 0)); // RG-05 : un parallèle suffit
}

function buildCards(checklist: Checklist): Card[] {
  return checklist.cards.map(([id, code, name, group, teams, flags]) => ({
    id,
    code,
    name,
    group,
    teams,
    rookie: Boolean(flags & 1),
    chase: Boolean(flags & 2),
  }));
}

// ------------------------------------------------------------------ une case

const CardTile = memo(function CardTile(props: {
  card: Card;
  quantity: number;
  parallels: number;
  photo: boolean;
  wanted: boolean;
}) {
  const { card, quantity, parallels, photo, wanted } = props;
  const owned = quantity > 0 || parallels > 0;
  // CA-19 : « 261, Mikel Brown Jr. RC, possédée, carte recherchée ».
  const label = [
    card.code,
    card.name,
    owned ? (quantity > 1 ? t("tile.copies", { count: quantity }) : t("tile.owned")) : t("tile.missing"),
    parallels > 0 ? tn("tile.parallels", parallels) : "",
    card.chase || wanted ? t("tile.wanted") : "",
  ]
    .filter(Boolean)
    .join(", ");
  return (
    <button className={`card${owned ? " owned" : ""}`} data-id={card.id} aria-label={label} style={{ height: 64 }}>
      <span className="code">{card.code}</span>
      <span className="label">{card.name}</span>
      <span className="marks" aria-hidden="true">
        {(card.chase || wanted) && <Flame fill={card.chase ? "currentColor" : "none"} />}
        {photo && <span className="mark-dot filled" />}
        {parallels > 0 && <span className="mark-dot" />}
        {quantity > 1 && <span>×{quantity}</span>}
      </span>
    </button>
  );
});

/** Tranche de cases : montée seulement près de l'écran, sinon remplacée par un espace de même hauteur. */
function Slice(props: { cards: Card[]; entries: Entries; columns: number }) {
  const { cards, entries, columns } = props;
  const ref = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(false);
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => setNear(entry.isIntersecting), { rootMargin: "700px 0px" });
    observer.observe(ref.current!);
    return () => observer.disconnect();
  }, []);
  const rows = Math.ceil(cards.length / columns);
  return (
    <div ref={ref} className="cards" style={{ gridTemplateColumns: `repeat(${columns}, 1fr)`, minHeight: rows * ROW_HEIGHT - 8 }}>
      {near &&
        cards.map((card) => {
          const entry = entries[card.id];
          return (
            <CardTile
              key={card.id}
              card={card}
              quantity={entry?.[0] ?? 0}
              parallels={entry?.[1] ?? 0}
              photo={Boolean(entry?.[2])}
              wanted={Boolean(entry?.[3])}
            />
          );
        })}
    </div>
  );
}

/** Sous-série. Une collection de 5 000 cartes ne monte que les cases visibles (CA-17). */
function GroupSection(props: { name: string; cards: Card[]; entries: Entries; columns: number }) {
  const { name, cards, entries, columns } = props;
  const owned = cards.reduce((count, card) => count + Number(isOwned(entries[card.id])), 0);
  const size = columns * SLICE_ROWS;
  const slices = [];
  for (let index = 0; index < cards.length; index += size) slices.push(cards.slice(index, index + size));
  return (
    <section aria-label={name}>
      <h2 className="group-header">
        <span>{name}</span>
        <span className="mono muted small">
          {owned} / {cards.length}
        </span>
      </h2>
      <div className="stack" style={{ gap: 8 }}>
        {slices.map((slice) => (
          <Slice key={slice[0].id} cards={slice} entries={entries} columns={columns} />
        ))}
      </div>
    </section>
  );
}

function useColumns(ref: React.RefObject<HTMLDivElement | null>): number {
  const [columns, setColumns] = useState(3);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () => {
      const width = node.clientWidth;
      setColumns(window.innerWidth < 700 ? 3 : Math.max(3, Math.floor((width + 8) / 138)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  });
  return columns;
}

// ------------------------------------------------------------------- l'écran

export function CollectionScreen() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const universes = useUniverses();
  const collection = useCollection(id);
  const checklist = useChecklist(collection.data?.series_id, collection.data?.series_version);
  const write = useCardWriter(id);
  const [, openCard] = useSheetParam("carte");
  const [panel, openPanel, closePanel] = useSheetParam("panneau");
  const grid = useRef<HTMLDivElement>(null);
  const columns = useColumns(grid);

  const cards = useMemo(() => (checklist.data ? buildCards(checklist.data) : []), [checklist.data]);
  const kinds = useMemo(() => [...new Set(checklist.data?.groups.map((g) => g.kind) ?? [])], [checklist.data]);

  const data = collection.data;
  const [team, setTeam] = useUrlState("equipe", data?.priority_team ?? "*");
  const [type, setType] = useUrlState("type", kinds.length > 1 && kinds.includes("base") ? "base" : "tout");
  const [stat, setStat] = useUrlState("vue", "all");
  const [query, setQuery] = useUrlState("q", "");
  const [quick, setQuick] = useState(false);
  const undo = useRef<number[]>([]);
  const longPress = useRef<{ timer: number; fired: boolean }>({ timer: 0, fired: false });

  const tokens = useMemo(() => {
    // Jetons de recherche, calculés à la première frappe seulement.
    if (!query || !checklist.data) return null;
    const { groups, teams } = checklist.data;
    return new Map(cards.map((c) => [c.id, cardTokens(c.code, c.name, groups[c.group].name, c.teams.map((i) => teams[i]))]));
  }, [Boolean(query), cards, checklist.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const view = useMemo(() => {
    if (!data || !checklist.data) return null;
    const entries = data.cards as Entries;
    const { groups, teams } = checklist.data;
    const teamIndex = team === "*" ? -1 : teams.indexOf(team);
    const inTeam = teamIndex < 0 ? cards : cards.filter((c) => c.teams.includes(teamIndex));
    const isWanted = (c: Card) => c.chase || Boolean(entries[c.id]?.[3]);

    // En-tête : avancement du périmètre affiché (série ou équipe), selon RG-15.
    const totalByKind: Record<string, number> = {};
    const ownedByKind: Record<string, number> = {};
    for (const c of inTeam) {
      const kind = groups[c.group].kind;
      totalByKind[kind] = (totalByKind[kind] ?? 0) + 1;
      if (isOwned(entries[c.id])) ownedByKind[kind] = (ownedByKind[kind] ?? 0) + 1;
    }
    const wanted = inTeam.filter(isWanted);

    let scope = type === "recherchees" ? wanted : type === "tout" ? inTeam : inTeam.filter((c) => groups[c.group].kind === type);
    const terms = parseQuery(query);
    if (terms.length && tokens) scope = scope.filter((c) => matches(terms, tokens.get(c.id)!));

    const counts = { all: scope.length, missing: 0, doubles: 0, owned: 0 };
    for (const c of scope) {
      const entry = entries[c.id];
      if (isOwned(entry)) counts.owned++;
      else counts.missing++;
      if ((entry?.[0] ?? 0) > 1) counts.doubles++; // RG-06 ; un parallèle n'est jamais un double
    }
    const visible = scope.filter((c) => {
      const entry = entries[c.id];
      if (stat === "missing") return !isOwned(entry);
      if (stat === "owned") return isOwned(entry);
      if (stat === "doubles") return (entry?.[0] ?? 0) > 1;
      return true;
    });
    const byGroup = new Map<number, Card[]>();
    for (const c of visible) {
      const list = byGroup.get(c.group);
      if (list) list.push(c);
      else byGroup.set(c.group, [c]);
    }

    const teamCounts = teams.map(() => [0, 0]);
    for (const c of cards) {
      for (const index of c.teams) {
        teamCounts[index][1]++;
        if (isOwned(entries[c.id])) teamCounts[index][0]++;
      }
    }
    return {
      entries,
      scope,
      counts,
      byGroup,
      totalByKind,
      ownedByKind,
      teamCounts,
      wanted: [wanted.filter((c) => isOwned(entries[c.id])).length, wanted.length],
      header: progress(totalByKind, ownedByKind),
    };
  }, [data, checklist.data, cards, team, type, stat, query, tokens]);

  if (collection.isPending) return <div className="screen"><Loading rows={6} /></div>;
  if (collection.isError) return <div className="screen"><ErrorNote error={collection.error} retry={() => collection.refetch()} /></div>;
  if (!data) return null;
  const isPersonal = data.series_id === null;
  const entries = data.cards as Entries;

  function pressCard(event: MouseEvent<HTMLDivElement>) {
    const tile = (event.target as HTMLElement).closest<HTMLElement>("[data-id]");
    if (!tile) return;
    const refId = Number(tile.dataset.id);
    if (longPress.current.fired) {
      longPress.current.fired = false;
      return;
    }
    if (!quick) return openCard(String(refId)); // RG-07 : toucher une case ouvre sa fiche, sans cocher
    const quantity = entries[refId]?.[0] ?? 0;
    if (quantity >= 999) return;
    write(refId, { quantity: quantity + 1 });
    undo.current.push(refId);
  }

  function pointerDown(event: PointerEvent<HTMLDivElement>) {
    if (!quick) return;
    const tile = (event.target as HTMLElement).closest<HTMLElement>("[data-id]");
    if (!tile) return;
    longPress.current.timer = window.setTimeout(() => {
      longPress.current.fired = true; // RG-07 : en saisie rapide, un appui long ouvre la fiche
      openCard(tile.dataset.id!);
    }, LONG_PRESS_MS);
  }
  const cancelLongPress = () => window.clearTimeout(longPress.current.timer);

  function undoLast() {
    const refId = undo.current.pop();
    if (refId === undefined) return;
    write(refId, { quantity: Math.max((entries[refId]?.[0] ?? 1) - 1, 0) });
  }

  async function copy(what: "missing" | "doubles") {
    if (!view) return;
    const codes = view.scope
      .filter((c) => (what === "missing" ? !isOwned(entries[c.id]) : (entries[c.id]?.[0] ?? 0) > 1))
      .map((c) => c.code);
    if (!codes.length) return toast(t("collection.copied.none"));
    await navigator.clipboard.writeText(formatCodeList(codes));
    toast(tn("collection.copied", codes.length), {
      // Ajout : format compact (« 1-12, 15 »), celui que les collectionneurs s'échangent.
      action: { label: t("collection.copyCompact"), run: () => void navigator.clipboard.writeText(formatCodeList(codes, true)) },
    });
  }

  const stats: { key: string; label: Key; count: number }[] = view
    ? [
        { key: "all", label: "collection.stat.all", count: view.counts.all },
        { key: "missing", label: "collection.stat.missing", count: view.counts.missing },
        { key: "doubles", label: "collection.stat.doubles", count: view.counts.doubles },
        { key: "owned", label: "collection.stat.owned", count: view.counts.owned },
      ]
    : [];
  const teams = checklist.data?.teams ?? [];
  const personalProgress = progress({ base: data.personal.length }, { base: data.personal.filter((c) => c.quantity > 0).length });
  const header = isPersonal ? personalProgress : (view?.header ?? { owned: data.owned, total: data.total, percent: data.percent, label: data.label });

  return (
    <main className="screen wide">
      <div className="topbar">
        <Link to="/collections" className="back">
          <ChevronLeft size={16} aria-hidden="true" />
          {t("nav.collections")}
        </Link>
        <button className="icon-button" aria-label={t("collection.menu")} onClick={() => openPanel("menu")}>
          <MoreHorizontal size={18} />
        </button>
      </div>

      <div className="spread" style={{ alignItems: "flex-end" }}>
        <div className="grow">
          <h1 className="title medium">{data.short_name}</h1>
          <p className="small muted" style={universes.style(data.universe_id)}>
            {[universes.name(data.universe_id), data.publisher].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="progress-figure">
          <strong>{header.label}</strong>
          <span className="mono small muted">{t("collection.owned", { owned: header.owned, total: header.total })}</span>
        </div>
      </div>
      <div className="bar" aria-hidden="true">
        <span style={{ width: `${header.percent}%` }} />
      </div>

      {!isPersonal && checklist.isPending && <div style={{ marginTop: 16 }}><Loading rows={5} /></div>}
      {checklist.isError && <div style={{ marginTop: 16 }}><ErrorNote error={checklist.error} retry={() => checklist.refetch()} /></div>}

      {view && (
        <div className="stack" style={{ marginTop: 14 }}>
          {teams.length > 0 && (
            // F-08 : barre d'équipe.
            <div className="cluster">
              {data.priority_team && (
                <button className="pill" aria-pressed={team === data.priority_team} onClick={() => setTeam(data.priority_team!)}>
                  <Star size={13} aria-hidden="true" />
                  {data.priority_team}
                  <span className="count">·{view.teamCounts[teams.indexOf(data.priority_team)]?.join("/")}</span>
                </button>
              )}
              <select
                className="pill"
                aria-label={t("collection.otherTeam")}
                value={team === data.priority_team ? "" : team}
                onChange={(event) => setTeam(event.target.value || (data.priority_team ?? "*"))}
              >
                <option value="">{t("collection.otherTeam")}</option>
                <option value="*">{t("collection.allTeams")}</option>
                {teams.map((name, index) => (
                  <option key={name} value={name}>
                    {name} · {view.teamCounts[index].join("/")}
                  </option>
                ))}
              </select>
            </div>
          )}

          <SearchBox value={query} onChange={setQuery} placeholder={t("collection.search")} />

          <div className="pills" role="group">
            {view.wanted[1] > 0 && (
              <button className="pill" aria-pressed={type === "recherchees"} onClick={() => setType(type === "recherchees" ? "tout" : "recherchees")}>
                <Flame size={13} aria-hidden="true" />
                {t("collection.wanted")}
                <span className="count">·{view.wanted.join("/")}</span>
              </button>
            )}
            {kinds.length > 1 &&
              kinds
                .filter((kind) => view.totalByKind[kind])
                .map((kind) => (
                  <button key={kind} className="pill" aria-pressed={type === kind} onClick={() => setType(type === kind ? "tout" : kind)}>
                    {t(`collection.kind.${kind}` as Key)}
                    <span className="count">
                      ·{view.ownedByKind[kind] ?? 0}/{view.totalByKind[kind]}
                    </span>
                  </button>
                ))}
          </div>

          <div className="tiles" role="group">
            {stats.map((item) => (
              <button key={item.key} className={`stat ${item.key}`} aria-pressed={stat === item.key} onClick={() => setStat(item.key)}>
                <strong>{item.count}</strong>
                {t(item.label)}
              </button>
            ))}
          </div>

          {quick ? (
            <div className="banner" role="status">
              <span>{t("collection.quick.on")}</span>
              <span className="cluster" style={{ flexWrap: "nowrap" }}>
                <button className="link" onClick={undoLast}>
                  {t("common.cancel")}
                </button>
                <button className="link" onClick={() => setQuick(false)}>
                  {t("collection.quick.stop")}
                </button>
              </span>
            </div>
          ) : (
            <div className="spread">
              <span className="small muted">{t("collection.hint")}</span>
              <button className="pill" onClick={() => { undo.current = []; setQuick(true); }}>
                {t("collection.quick")}
              </button>
            </div>
          )}
        </div>
      )}

      <div ref={grid} onClick={pressCard} onPointerDown={pointerDown} onPointerUp={cancelLongPress} onPointerLeave={cancelLongPress} onPointerCancel={cancelLongPress} onContextMenu={(event) => quick && event.preventDefault()}>
        {view &&
          checklist.data!.groups.map((group, index) => {
            const groupCards = view.byGroup.get(index);
            return groupCards ? <GroupSection key={group.id} name={group.name} cards={groupCards} entries={view.entries} columns={columns} /> : null;
          })}
        {view && view.byGroup.size === 0 && <p className="empty" style={{ marginTop: 16 }}>{t("collection.noMatch")}</p>}
      </div>

      <PersonalCards collectionId={id} cards={data.personal} standalone={isPersonal} />

      {view && (
        <div className="dock">
          <button className="button" onClick={() => openPanel("import")}>
            <Download size={16} aria-hidden="true" />
            {t("collection.import")}
          </button>
          <button className="button primary" onClick={() => copy(stat === "doubles" ? "doubles" : "missing")}>
            {stat === "doubles" ? t("collection.copyDoubles") : t("collection.copyMissing")}
          </button>
        </div>
      )}
      {isPersonal && (
        <div className="dock">
          <button className="button" onClick={() => openPanel("import")}>
            <Download size={16} aria-hidden="true" />
            {t("collection.import")}
          </button>
        </div>
      )}

      {panel === "import" && <ImportSheet collectionId={id} onClose={closePanel} />}
      {panel === "menu" && (
        <MenuSheet
          collection={data}
          teams={teams}
          onClose={closePanel}
          onGone={() => navigate("/collections", { replace: true })}
          exportCsv={() => exportCsv(data, checklist.data, cards)}
        />
      )}
    </main>
  );
}

/** Export CSV de la collection (F-07), construit à partir des données déjà chargées. */
function exportCsv(collection: S["CollectionDetailOut"], checklist: Checklist | undefined, cards: Card[]) {
  const quote = (value: string | number) => `"${String(value).replaceAll('"', '""')}"`;
  const lines = [["code", "nom", "sous-série", "équipes", "quantité", "parallèles", "recherchée"].join(";")];
  for (const c of cards) {
    const entry = (collection.cards as Entries)[c.id];
    const teams = c.teams.map((i) => checklist!.teams[i]).join(" / ");
    lines.push([quote(c.code), quote(c.name), quote(checklist!.groups[c.group].name), quote(teams), entry?.[0] ?? 0, entry?.[1] ?? 0, entry?.[3] ? "oui" : ""].join(";"));
  }
  for (const c of collection.personal) lines.push([quote(c.code), quote(c.name), quote("hors liste"), "", c.quantity, 0, ""].join(";"));
  const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${collection.name}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

// ------------------------------------------------------------------ panneaux

function ImportSheet({ collectionId, onClose }: { collectionId: number; onClose: () => void }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<S["ImportCodesOut"] | null>(null);
  const run = useApiMutation(
    () => api<S["ImportCodesOut"]>(`/collections/${collectionId}/import-codes`, { body: { text } }),
    (client, data) => {
      setResult(data);
      refreshOwnership(client);
    },
  );
  return (
    <Sheet title={t("import.title")} onClose={onClose}>
      <div className="stack">
        <p className="small muted">{t("import.text")}</p>
        <label className="field">
          <span className="sr-only">{t("import.title")}</span>
          <textarea rows={6} value={text} placeholder={t("import.placeholder")} onChange={(e) => setText(e.target.value)} autoFocus />
        </label>
        {run.isError && <p className="error-text" role="alert">{apiErrorText(run.error)}</p>}
        {result && (
          <div className="note" role="status">
            <div>
              <strong>{t("import.result", { checked: result.checked, already: result.already })}</strong>
              {result.unknown.length > 0 && <p>{t("import.unknown", { codes: result.unknown.join(", ") })}</p>}
            </div>
          </div>
        )}
        <button className="button primary big block" disabled={!text.trim() || run.isPending} onClick={() => run.mutate(undefined)}>
          {t("import.submit")}
        </button>
      </div>
    </Sheet>
  );
}

function MenuSheet(props: {
  collection: S["CollectionDetailOut"];
  teams: string[];
  onClose: () => void;
  onGone: () => void;
  exportCsv: () => void;
}) {
  const { collection, teams, onClose, onGone } = props;
  const [confirming, setConfirming] = useState(false);
  const patch = useApiMutation((body: S["CollectionIn"]) => api(`/collections/${collection.id}`, { method: "PATCH", body }));
  const remove = useApiMutation(
    () => api(`/collections/${collection.id}`, { method: "DELETE" }),
    (client) => {
      client.removeQueries({ queryKey: keys.collection(collection.id) });
      refreshOwnership(client);
      toast(t("collection.deleted"));
      onGone();
    },
  );
  if (confirming) {
    // RG-08 : confirmation en deux temps.
    return (
      <Confirm
        title={t("collection.menu.delete")}
        text={`${t("collection.menu.delete.hint")} ${t("confirm.sure")}`}
        action={t("confirm.delete")}
        busy={remove.isPending}
        onConfirm={() => remove.mutate(undefined)}
        onClose={() => setConfirming(false)}
      />
    );
  }
  return (
    <Sheet title={collection.short_name} onClose={onClose}>
      <div className="stack">
        {teams.length > 0 && (
          <Field label={t("collection.menu.priorityTeam")}>
            <select
              value={collection.priority_team ?? ""}
              onChange={(event) =>
                patch.mutate(event.target.value ? { priority_team: event.target.value } : { clear_priority_team: true })
              }
            >
              <option value="">{t("collection.menu.noTeam")}</option>
              {teams.map((team) => (
                <option key={team}>{team}</option>
              ))}
            </select>
          </Field>
        )}
        {patch.isError && <p className="error-text" role="alert">{apiErrorText(patch.error)}</p>}
        {collection.series_id !== null && (
          <>
            <Link to="/profil/partage" className="button block">{t("collection.menu.share")}</Link>
            <button className="button block" onClick={props.exportCsv}>{t("collection.menu.export")}</button>
            <div>
              <button
                className="button block"
                onClick={() =>
                  patch.mutate({ status: "reserve" }, { onSuccess: () => { toast(t("collection.unfollowed")); onGone(); } })
                }
              >
                {t("collection.menu.unfollow")}
              </button>
              <p className="small muted" style={{ marginTop: 6 }}>{t("collection.menu.unfollow.hint")}</p>
            </div>
          </>
        )}
        <button className="button danger block" onClick={() => setConfirming(true)}>
          {t("collection.menu.delete")}
        </button>
      </div>
    </Sheet>
  );
}

/** RG-03 : cartes hors catalogue ajoutées par l'utilisateur, visibles de lui seul. */
function PersonalCards(props: { collectionId: number; cards: S["PersonalCardOut"][]; standalone: boolean }) {
  const { collectionId, cards, standalone } = props;
  const [editing, setEditing] = useState<S["PersonalCardOut"] | "new" | null>(null);
  const sorted = [...cards].sort((a, b) => compareCodes(a.code, b.code));
  return (
    <section aria-label={t("collection.personal")}>
      {(cards.length > 0 || standalone) && (
        <h2 className="group-header">
          <span>{standalone ? t("collection.stat.all") : t("collection.personal")}</span>
          <span className="mono muted small">{cards.filter((c) => c.quantity > 0).length} / {cards.length}</span>
        </h2>
      )}
      <div className="cards">
        {sorted.map((card) => (
          <button key={card.id} className={`card${card.quantity > 0 ? " owned" : ""}`} style={{ height: 64 }} onClick={() => setEditing(card)}>
            <span className="code">{card.code}</span>
            <span className="label">{card.name}</span>
            {card.quantity > 1 && <span className="marks" aria-hidden="true">×{card.quantity}</span>}
          </button>
        ))}
      </div>
      <button className="button quiet" style={{ marginTop: 10 }} onClick={() => setEditing("new")}>
        <Plus size={16} aria-hidden="true" />
        {t("collection.addPersonal")}
      </button>
      {editing && <PersonalCardSheet collectionId={collectionId} card={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </section>
  );
}

function PersonalCardSheet(props: { collectionId: number; card: S["PersonalCardOut"] | null; onClose: () => void }) {
  const { collectionId, card, onClose } = props;
  const [code, setCode] = useState(card?.code ?? "");
  const [name, setName] = useState(card?.name ?? "");
  const [quantity, setQuantity] = useState(card?.quantity ?? 1);
  const [confirming, setConfirming] = useState(false);
  const save = useApiMutation(
    () =>
      card
        ? api(`/personal-cards/${card.id}`, { method: "PATCH", body: { name, quantity } })
        : api(`/collections/${collectionId}/personal-cards`, { body: { code, name, quantity } }),
    (client) => {
      refreshOwnership(client);
      onClose();
    },
  );
  const remove = useApiMutation(
    () => api(`/personal-cards/${card!.id}`, { method: "DELETE" }),
    (client) => {
      refreshOwnership(client);
      onClose();
    },
  );
  if (confirming) {
    return <Confirm title={t("common.delete")} text={t("confirm.sure")} action={t("confirm.delete")} onConfirm={() => remove.mutate(undefined)} onClose={() => setConfirming(false)} busy={remove.isPending} />;
  }
  return (
    <Sheet title={card ? t("card.title", { code: card.code }) : t("collection.addPersonal")} onClose={onClose}>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); save.mutate(undefined); }}>
        {!card && (
          <Field label={t("add.code")}>
            <input value={code} onChange={(e) => setCode(e.target.value)} required autoCapitalize="characters" autoFocus />
          </Field>
        )}
        <Field label={t("add.name")}>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div>
          <span className="label">{t("add.quantity")}</span>
          <div className="stepper" style={{ marginTop: 6 }}>
            <button type="button" aria-label={t("card.less")} onClick={() => setQuantity(Math.max(0, quantity - 1))}>−</button>
            <output>{quantity}</output>
            <button type="button" aria-label={t("card.more")} onClick={() => setQuantity(Math.min(999, quantity + 1))}>+</button>
          </div>
        </div>
        {save.isError && <p className="error-text" role="alert">{apiErrorText(save.error)}</p>}
        <button className="button primary big block" disabled={save.isPending}>{t("common.save")}</button>
        {card && <button type="button" className="button danger block" onClick={() => setConfirming(true)}>{t("common.delete")}</button>}
      </form>
    </Sheet>
  );
}
