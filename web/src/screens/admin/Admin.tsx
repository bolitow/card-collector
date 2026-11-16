import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom";

import { api, type S } from "@/api/client";
import { keys, useApiMutation, useCatalogIndex, useMe } from "@/api/hooks";
import { t, type Key } from "@/i18n";
import { fileSize, shortDate } from "@/lib/format";
import { TotpSheet } from "@/screens/Profile";
import { apiErrorText, ErrorNote, Field, Loading, Photo } from "@/ui/parts";
import { toast } from "@/ui/toast";

type Group = S["DraftGroup"];
type Draft = { groups: Group[] }; // le serveur renvoie toujours la liste, même vide
const KINDS = ["base", "insert", "special", "relic", "auto"] as const;

/** Administration (section 6.6) : réservée aux administrateurs, derrière la double authentification. */
export default function Admin() {
  const me = useMe();
  const client = useQueryClient();
  const [code, setCode] = useState("");
  const [enrolling, setEnrolling] = useState(false);
  const elevate = useApiMutation(() => api("/auth/totp", { body: { code } }), () => void client.invalidateQueries({ queryKey: keys.me }));
  const access = me.data?.admin_access;

  if (!me.data) return <div className="screen"><Loading /></div>;
  if (!access) return <div className="screen"><ErrorNote error={new Error("forbidden")} /></div>;
  if (access === "totp_setup_required") {
    return (
      <main className="screen stack loose">
        <h1 className="title">{t("admin.title")}</h1>
        <p>{t("admin.totp.setup")}</p>
        <button className="button primary big block" onClick={() => setEnrolling(true)}>{t("profile.totp.setup")}</button>
        {enrolling && <TotpSheet onClose={() => setEnrolling(false)} />}
      </main>
    );
  }
  if (access === "totp_required") {
    return (
      <main className="screen stack loose">
        <h1 className="title">{t("admin.title")}</h1>
        <form className="stack" onSubmit={(event) => { event.preventDefault(); elevate.mutate(undefined); }}>
          <Field label={t("admin.totp.enter")} error={elevate.isError ? apiErrorText(elevate.error) : null}>
            <input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} required autoFocus />
          </Field>
          <button className="button primary big block" disabled={elevate.isPending}>{t("admin.totp.submit")}</button>
        </form>
      </main>
    );
  }

  const tabs: { to: string; label: Key; end?: boolean }[] = [
    { to: "/admin", label: "admin.tab.imports", end: true },
    { to: "/admin/series", label: "admin.tab.series" },
    { to: "/admin/file", label: "admin.tab.queue" },
    { to: "/admin/utilisateurs", label: "admin.tab.users" },
    { to: "/admin/tableau", label: "admin.tab.stats" },
    { to: "/admin/journal", label: "admin.tab.audit" },
  ];
  return (
    <main className="screen wide stack loose">
      <h1 className="title medium">{t("admin.title")}</h1>
      <nav className="tabs">
        {tabs.map((tab) => <NavLink key={tab.to} to={tab.to} end={tab.end}>{t(tab.label)}</NavLink>)}
      </nav>
      <Routes>
        <Route index element={<Imports />} />
        <Route path="imports/:id" element={<ImportDetail />} />
        <Route path="series" element={<SeriesAdmin />} />
        <Route path="file" element={<Queue />} />
        <Route path="utilisateurs" element={<Users />} />
        <Route path="tableau" element={<Stats />} />
        <Route path="journal" element={<Audit />} />
      </Routes>
    </main>
  );
}

function Steps({ current }: { current: number }) {
  const labels: Key[] = ["admin.import.step1", "admin.import.step2", "admin.import.step3", "admin.import.step4"];
  return (
    <ol className="steps">
      {labels.map((label, index) => <li key={label} aria-current={index + 1 === current ? "step" : undefined}>{index + 1}. {t(label)}</li>)}
    </ol>
  );
}

// ------------------------------------------------------------------ imports

/** F-36, étape 1 : source, univers, éditeur. */
function Imports() {
  const navigate = useNavigate();
  const index = useCatalogIndex();
  const publishers = useQuery({ queryKey: ["admin", "publishers"], queryFn: () => api<S["PublisherOut"][]>("/admin/publishers") });
  const list = useQuery({ queryKey: ["admin", "imports"], queryFn: () => api<S["ImportOut"][]>("/admin/imports") });
  const [form, setForm] = useState({ universe_id: "", publisher_id: "", series_name: "", season: "", source: "", text: "", use_ai: true });
  const [file, setFile] = useState<File | null>(null);
  const create = useApiMutation(
    () => {
      if (!file) return api<S["ImportOut"]>("/admin/imports", { body: { ...form, universe_id: Number(form.universe_id), publisher_id: Number(form.publisher_id) } });
      const data = new FormData();
      data.append("file", file);
      for (const [key, value] of Object.entries(form)) if (key !== "text") data.append(key, String(value));
      return api<S["ImportOut"]>("/admin/imports/pdf", { form: data });
    },
    (_, created) => navigate(`/admin/imports/${created.id}`),
  );
  const set = (field: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm({ ...form, [field]: event.target.value });

  return (
    <div className="stack loose">
      <section className="panel stack">
        <h2 className="heading">{t("admin.import.new")}</h2>
        <Steps current={1} />
        <form className="stack" onSubmit={(event) => { event.preventDefault(); create.mutate(undefined); }}>
          <div className="cluster" style={{ alignItems: "flex-start" }}>
            <Field label={t("admin.import.universe")}>
              <select value={form.universe_id} onChange={set("universe_id")} required>
                <option value="" />
                {index.data?.universes.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </select>
            </Field>
            <Field label={t("admin.import.publisher")}>
              <select value={form.publisher_id} onChange={set("publisher_id")} required>
                <option value="" />
                {publishers.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <Field label={t("admin.import.season")}><input value={form.season} onChange={set("season")} placeholder="2025/26" style={{ width: 120 }} /></Field>
          </div>
          <Field label={t("admin.import.name")}><input value={form.series_name} onChange={set("series_name")} placeholder="Topps Chrome Football 2026" /></Field>
          <Field label={t("admin.import.source")}><input value={form.source} onChange={set("source")} /></Field>
          <Field label={t("admin.import.pdf")}><input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
          {!file && <Field label={t("admin.import.text")}><textarea rows={8} value={form.text} onChange={set("text")} className="mono" /></Field>}
          <label className="check">
            <input type="checkbox" checked={form.use_ai} onChange={(e) => setForm({ ...form, use_ai: e.target.checked })} />
            <span>{t("admin.import.useAi")}</span>
          </label>
          {create.isError && <p className="error-text" role="alert">{apiErrorText(create.error)}</p>}
          <button className="button primary" disabled={create.isPending || (!file && !form.text.trim())}>{t("admin.import.start")}</button>
        </form>
      </section>

      <div>
        {list.data?.map((item) => (
          <Link key={item.id} to={`/admin/imports/${item.id}`} className="row">
            <span className="grow">
              <span className="name" style={{ display: "block" }}>{item.series_name || `#${item.id}`}</span>
              <span className="meta">{shortDate(item.created_at)} · {t("admin.import.cards", { cards: Number(item.counters.cards ?? 0), groups: Number(item.counters.groups ?? 0) })}</span>
            </span>
            <span className="chip">{item.status}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

/** F-36, étapes 2 à 4 : analyse, relecture, publication. */
function ImportDetail() {
  const id = Number(useParams().id);
  const client = useQueryClient();
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["admin", "import", id],
    queryFn: () => api<S["ImportDetailOut"]>(`/admin/imports/${id}`),
    refetchInterval: (q) => (q.state.data?.status === "analyzing" ? 2000 : false),
  });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [meta, setMeta] = useState({ series_name: "", season: "", source: "" });
  const [open, setOpen] = useState<number | null>(null);
  const [diff, setDiff] = useState<Record<string, any> | null>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const record = query.data;

  useEffect(() => {
    if (record?.status === "review") {
      setDraft({ groups: record.draft.groups ?? [] });
      setMeta({ series_name: record.series_name, season: record.season, source: record.source });
    }
  }, [record?.status, record?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useApiMutation(
    () => api<S["ImportDetailOut"]>(`/admin/imports/${id}`, { method: "PATCH", body: { ...meta, draft } }),
    (_, saved) => {
      client.setQueryData(["admin", "import", id], saved);
      setDraft({ groups: saved.draft.groups ?? [] });
    },
  );
  const publish = useApiMutation(
    () => api<{ series_id: number; version: number }>(`/admin/imports/${id}/publish`, { method: "POST" }),
    (_, result) => {
      void client.invalidateQueries({ queryKey: ["admin"] });
      void client.invalidateQueries({ queryKey: ["series"] });
      toast(t("admin.import.published", { version: result.version }));
      navigate("/admin/series");
    },
  );

  if (query.isPending) return <Loading />;
  if (query.isError || !record) return <ErrorNote error={query.error} />;
  if (record.status === "analyzing") return <div className="stack"><Steps current={2} /><p className="note" role="status">{t("admin.import.analyzing")}</p></div>;
  if (record.status === "failed") return <ErrorNote error={new Error(record.error)} />;
  if (!draft) return <Loading />;

  const updateGroup = (index: number, patch: Partial<Group>) => setDraft({ groups: draft.groups.map((g, i) => (i === index ? { ...g, ...patch } : g)) });
  const updateCard = (groupIndex: number, cardIndex: number, patch: Partial<S["DraftCard"]>) =>
    updateGroup(groupIndex, { cards: (draft.groups[groupIndex].cards ?? []).map((c, i) => (i === cardIndex ? { ...c, ...patch } : c)) });
  const split = (value: string) => value.split("/").map((part) => part.trim()).filter(Boolean);
  const blocking = record.anomalies.filter((a) => a.blocking).length;

  async function showDiff() {
    await save.mutateAsync(undefined);
    setDiff(await api(`/admin/imports/${id}/diff`));
  }

  return (
    <div className="stack loose">
      <Steps current={diff ? 4 : 3} />
      <section className="panel stack">
        <div className="cluster" style={{ alignItems: "flex-start" }}>
          <div className="grow"><Field label={t("admin.import.name")}><input value={meta.series_name} onChange={(e) => setMeta({ ...meta, series_name: e.target.value })} /></Field></div>
          <Field label={t("admin.import.season")}><input value={meta.season} onChange={(e) => setMeta({ ...meta, season: e.target.value })} style={{ width: 120 }} /></Field>
        </div>
        <Field label={t("admin.import.source")}><input value={meta.source} onChange={(e) => setMeta({ ...meta, source: e.target.value })} /></Field>
        {record.name_problems.map((problem) => <p key={problem} className="note warn">{problem}</p>)}
        <p className="small muted">{t("admin.import.cards", { cards: Number(record.counters.cards ?? 0), groups: Number(record.counters.groups ?? 0) })}</p>
      </section>

      <section className="stack">
        <h2 className="heading">{t("admin.import.anomalies")} <span className="mono muted">{record.anomalies.length}</span></h2>
        {record.anomalies.length === 0 && <p className="small muted">{t("admin.import.anomalies.none")}</p>}
        <div>
          {record.anomalies.slice(0, 60).map((anomaly, index) => (
            <button key={index} className="row" onClick={() => setOpen(anomaly.group)}>
              <span className="grow">
                <span className="name" style={{ display: "block", whiteSpace: "normal" }}>{anomaly.detail}</span>
                {anomaly.proposal && <span className="meta" style={{ whiteSpace: "normal" }}>{anomaly.proposal}</span>}
              </span>
              <span className={`chip ${anomaly.blocking ? "owned" : "outline"}`}>{anomaly.blocking ? t("admin.import.blocking") : anomaly.type}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="stack">
        {draft.groups.map((group, groupIndex) => {
          const flagged = new Set(record.anomalies.filter((a) => a.group === groupIndex).map((a) => a.code));
          return (
            <details key={groupIndex} className="panel" open={open === groupIndex} onToggle={(event) => (event.currentTarget.open ? setOpen(groupIndex) : open === groupIndex && setOpen(null))}>
              <summary className="spread" style={{ cursor: "pointer" }}>
                <strong>{group.name || "—"}</strong>
                <span className="small muted">{t(`collection.kind.${group.kind}` as Key)} · {(group.cards ?? []).length}{flagged.size > 0 && ` · ${flagged.size} ⚠`}</span>
              </summary>
              {open === groupIndex && (
                <div className="stack" style={{ marginTop: 12 }}>
                  <div className="cluster" style={{ alignItems: "flex-start" }}>
                    <div className="grow"><Field label={t("admin.import.group.name")}><input value={group.name} onChange={(e) => updateGroup(groupIndex, { name: e.target.value })} /></Field></div>
                    <Field label={t("admin.import.group.kind")}>
                      <select value={group.kind} onChange={(e) => updateGroup(groupIndex, { kind: e.target.value as Group["kind"] })}>
                        {KINDS.map((kind) => <option key={kind} value={kind}>{t(`collection.kind.${kind}` as Key)}</option>)}
                      </select>
                    </Field>
                    <Field label={t("admin.import.group.prefix")}><input value={group.prefix ?? ""} onChange={(e) => updateGroup(groupIndex, { prefix: e.target.value.toUpperCase() })} style={{ width: 100 }} /></Field>
                  </div>
                  <div style={{ overflowX: "auto" }}>
                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th style={{ width: 110 }}>{t("admin.import.card.code")}</th>
                          <th>{t("admin.import.card.names")}</th>
                          <th>{t("admin.import.card.teams")}</th>
                          <th style={{ width: 44 }}>{t("admin.import.card.rookie")}</th>
                          <th style={{ width: 44 }} />
                        </tr>
                      </thead>
                      <tbody>
                        {(group.cards ?? []).map((card, cardIndex) => (
                          <tr key={cardIndex} className={flagged.has(card.code) || flagged.has(`${group.prefix}-${card.code}`) ? "flagged" : undefined}>
                            <td><input className="mono" value={card.code} aria-label={t("admin.import.card.code")} onChange={(e) => updateCard(groupIndex, cardIndex, { code: e.target.value })} /></td>
                            <td><input value={(card.names ?? []).join(" / ")} aria-label={t("admin.import.card.names")} onChange={(e) => updateCard(groupIndex, cardIndex, { names: split(e.target.value) })} /></td>
                            <td><input value={(card.teams ?? []).join(" / ")} aria-label={t("admin.import.card.teams")} onChange={(e) => updateCard(groupIndex, cardIndex, { teams: split(e.target.value) })} /></td>
                            <td><input type="checkbox" checked={card.rookie ?? false} aria-label={t("admin.import.card.rookie")} onChange={(e) => updateCard(groupIndex, cardIndex, { rookie: e.target.checked })} style={{ width: 20, minHeight: 20 }} /></td>
                            <td><button aria-label={t("common.delete")} onClick={() => updateGroup(groupIndex, { cards: (group.cards ?? []).filter((_, i) => i !== cardIndex) })}>✕</button></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="cluster">
                    <button className="button" onClick={() => updateGroup(groupIndex, { cards: [...(group.cards ?? []), { code: "", names: [], teams: [], rookie: false }] })}>{t("admin.import.card.add")}</button>
                    <button className="button danger" onClick={() => { setDraft({ groups: draft.groups.filter((_, i) => i !== groupIndex) }); setOpen(null); }}>{t("admin.import.group.delete")}</button>
                  </div>
                </div>
              )}
            </details>
          );
        })}
        <button className="button" onClick={() => { setDraft({ groups: [...draft.groups, { name: "", kind: "insert", prefix: "", cards: [] }] }); setOpen(draft.groups.length); }}>{t("admin.import.group.add")}</button>
      </section>

      {(save.isError || publish.isError) && <p className="error-text" role="alert">{apiErrorText(save.error ?? publish.error)}</p>}
      <div className="cluster">
        <button className="button" disabled={save.isPending} onClick={() => save.mutate(undefined, { onSuccess: () => toast(t("admin.import.saved")) })}>{t("admin.import.saveDraft")}</button>
        <button className="button dark" disabled={save.isPending || blocking > 0} onClick={showDiff}>{t("admin.import.review")}</button>
      </div>

      {diff && (
        // F-38 : les changements sont montrés avant publication.
        <section className="panel stack">
          <h2 className="heading">{t("admin.import.diff")}</h2>
          <div className="cluster">
            {(["added", "renamed", "recoded", "moved", "removed", "unchanged"] as const).map((kind) => (
              <span key={kind} className="chip">{t(`admin.import.diff.${kind}` as Key)} <span className="mono">{diff.counts[kind]}</span></span>
            ))}
          </div>
          {diff.renamed.map((row: Record<string, string>) => <p key={row.code} className="small"><span className="mono">#{row.code}</span> {row.before} → <strong>{row.after}</strong></p>)}
          {diff.recoded.map((row: Record<string, string>) => <p key={row.after} className="small"><span className="mono">{row.before} → {row.after}</span> {row.name}</p>)}
          {diff.removed.map((row: Record<string, string | number>) => (
            <p key={row.code} className="small"><span className="mono">#{row.code}</span> {row.name}{Number(row.owners) > 0 && <strong> — {t("admin.import.diff.owners", { count: row.owners })}</strong>}</p>
          ))}
          <button className="button primary big" disabled={publish.isPending} onClick={() => publish.mutate(undefined)}>{t("admin.import.publish")}</button>
        </section>
      )}
    </div>
  );
}

// ------------------------------------------------------------------- séries

function SeriesAdmin() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const list = useQuery({ queryKey: ["admin", "series", q], queryFn: () => api<S["AdminSeriesOut"][]>("/admin/series", { params: { q } }) });
  const edit = useApiMutation((id: number) => api<S["ImportOut"]>(`/admin/series/${id}/edit`, { method: "POST" }), (_, created) => navigate(`/admin/imports/${created.id}`));
  const patch = useApiMutation(
    ({ id, status }: { id: number; status: "published" | "hidden" }) => api(`/admin/series/${id}`, { method: "PATCH", body: { status } }),
    () => void client.invalidateQueries({ queryKey: ["admin", "series"] }),
  );
  return (
    <div className="stack">
      <input className="input" placeholder={t("catalog.search")} value={q} onChange={(e) => setQ(e.target.value)} />
      <div>
        {list.data?.map((series) => (
          <div key={series.id} className="row">
            <span className="grow">
              <span className="name" style={{ display: "block" }}>{series.name}</span>
              <span className="meta">v{series.version} · {series.card_count} · {t("admin.series.followers")} {series.followers} · {series.status}</span>
            </span>
            <button className="button" disabled={edit.isPending} onClick={() => edit.mutate(series.id)}>{t("admin.series.edit")}</button>
            <button className="button" onClick={() => patch.mutate({ id: series.id, status: series.status === "published" ? "hidden" : "published" })}>
              {series.status === "published" ? t("admin.series.hide") : t("admin.series.show")}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------- file de travail

/** F-48 : demandes de séries et signalements, avec statut et réponse à l'utilisateur. */
function Queue() {
  const client = useQueryClient();
  const queue = useQuery({ queryKey: ["admin", "queue"], queryFn: () => api<S["QueueItemOut"][]>("/admin/queue") });
  const [replies, setReplies] = useState<Record<string, string>>({});
  const refresh = () => void client.invalidateQueries({ queryKey: ["admin", "queue"] });
  const answer = useApiMutation(
    ({ item, status }: { item: S["QueueItemOut"]; status: string }) =>
      api(`/admin/queue/${item.kind}/${item.id}`, { method: "PATCH", body: { status, admin_reply: replies[`${item.kind}${item.id}`] ?? "" } }),
    refresh,
  );
  const removePhoto = useApiMutation((item: S["QueueItemOut"]) => api(`/admin/photos/${item.photo_id}`, { method: "DELETE", params: { reason: item.detail.slice(0, 200) } }), refresh);
  if (queue.isPending) return <Loading />;
  if (!queue.data?.length) return <p className="empty">{t("admin.queue.empty")}</p>;
  return (
    <div className="stack">
      {queue.data.map((item) => {
        const key = `${item.kind}${item.id}`;
        const actions = item.kind === "request" ? [["accepted", t("admin.queue.accept")], ["declined", t("admin.queue.decline")]] : [["resolved", t("admin.queue.resolve")], ["dismissed", t("admin.queue.dismiss")]];
        return (
          <div key={key} className="panel stack">
            <div className="spread">
              <strong>{item.title}</strong>
              <span className="small muted">{item.author ?? "—"} · {shortDate(item.created_at)}{(item.votes ?? 0) > 1 && ` · ${item.votes} ×`}</span>
            </div>
            <p className="small" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{item.detail}</p>
            {item.photo_id && (
              <div className="cluster">
                <Photo id={item.photo_id} size="medium" alt="" shareToken={null} />
                <span className="small muted">{item.target_pseudo}</span>
                <button className="button danger" disabled={removePhoto.isPending} onClick={() => removePhoto.mutate(item)}>{t("admin.queue.removePhoto")}</button>
              </div>
            )}
            <Field label={t("admin.queue.reply")}>
              <textarea rows={2} value={replies[key] ?? ""} onChange={(e) => setReplies({ ...replies, [key]: e.target.value })} />
            </Field>
            <div className="cluster">
              {actions.map(([status, label]) => (
                <button key={status} className="button" disabled={answer.isPending} onClick={() => answer.mutate({ item, status })}>{label}</button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------- utilisateurs

/** F-49 : recherche, suspension, suppression à la demande, quotas d'IA. Chaque action est motivée. */
function Users() {
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const [reason, setReason] = useState("");
  const users = useQuery({ queryKey: ["admin", "users", q], queryFn: () => api<S["AdminUserOut"][]>("/admin/users", { params: { q } }) });
  const update = useApiMutation(
    ({ id, ...body }: Partial<S["AdminUserIn"]> & { id: string }) => api(`/admin/users/${id}`, { method: "PATCH", body: { reason, ...body } }),
    () => void client.invalidateQueries({ queryKey: ["admin", "users"] }),
  );
  const ready = reason.trim().length >= 3;
  return (
    <div className="stack">
      <input className="input" placeholder={t("admin.users.search")} value={q} onChange={(e) => setQ(e.target.value)} />
      <Field label={t("admin.users.reason")} error={update.isError ? apiErrorText(update.error) : null}>
        <input value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <div>
        {users.data?.map((user) => (
          <div key={user.id} className="row" style={{ flexWrap: "wrap" }}>
            <span className="grow">
              <span className="name" style={{ display: "block" }}>{user.pseudo} <span className="muted" style={{ fontWeight: 400 }}>{user.email}</span></span>
              <span className="meta">{user.role} · {user.status} · {shortDate(user.created_at)} · {user.collections} coll. · {user.photos} photos</span>
            </span>
            <button className="button" disabled={!ready} onClick={() => update.mutate({ id: user.id, status: user.status === "suspended" ? "active" : "suspended" })}>
              {user.status === "suspended" ? t("admin.users.restore") : t("admin.users.suspend")}
            </button>
            <button className="button" disabled={!ready} title={t("admin.users.quota")} onClick={() => {
              const value = window.prompt(t("admin.users.quota"), `${user.ai_quota_day ?? ""}/${user.ai_quota_month ?? ""}`);
              if (value === null) return;
              const [day, month] = value.split("/").map((part) => part.trim());
              update.mutate(day || month ? { id: user.id, ai_quota_day: day ? Number(day) : null, ai_quota_month: month ? Number(month) : null } : { id: user.id, reset_quotas: true });
            }}>
              IA {user.ai_quota_day ?? "–"}/{user.ai_quota_month ?? "–"}
            </button>
            <button className="button danger" disabled={!ready} onClick={() => window.confirm(`${t("admin.users.delete")} : ${user.email} ?`) && update.mutate({ id: user.id, delete: true })}>
              {t("admin.users.delete")}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function Stats() {
  const stats = useQuery({ queryKey: ["admin", "stats"], queryFn: () => api<S["StatsOut"]>("/admin/stats") });
  if (!stats.data) return <Loading />;
  const data = stats.data;
  const cells: [Key, string | number][] = [
    ["admin.stats.users", data.users],
    ["admin.stats.new", data.users_30d],
    ["admin.stats.active", data.active_30d],
    ["admin.stats.photos", `${data.photos} · ${fileSize(data.photo_bytes)}`],
    ["admin.stats.ai", data.ai_calls_30d],
    ["admin.stats.aiCost", `${Number(data.ai_cost_30d).toFixed(2)} $`],
    ["admin.stats.queue", data.queue_open],
  ];
  return (
    <div className="stack loose">
      <div className="tiles" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        {cells.map(([label, value]) => <div key={label} className="stat"><strong>{value}</strong>{t(label)}</div>)}
      </div>
      <section className="stack">
        <h2 className="heading">{t("admin.stats.top")}</h2>
        <div className="table">
          {data.top_series.map((row) => <div key={String(row.name)}><strong>{String(row.name)}</strong><span /><span className="mono">{String(row.followers)}</span></div>)}
        </div>
      </section>
    </div>
  );
}

function Audit() {
  const log = useQuery({ queryKey: ["admin", "audit"], queryFn: () => api<S["AuditOut"][]>("/admin/audit") });
  if (!log.data) return <Loading />;
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="admin-table">
        <tbody>
          {log.data.map((row) => (
            <tr key={row.id}>
              <td className="mono">{shortDate(row.created_at)}</td>
              <td><strong>{row.action}</strong></td>
              <td className="mono">{row.target}</td>
              <td>{row.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
