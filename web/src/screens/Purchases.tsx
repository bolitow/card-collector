import { BarChart3, Camera, ChevronLeft, Eye, Pencil } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, type S } from "@/api/client";
import { keys, refreshOwnership, useApiMutation, useMe, usePurchase, usePurchases } from "@/api/hooks";
import { t, tn } from "@/i18n";
import { money, shortDate, today } from "@/lib/format";
import { apiErrorText, Confirm, ErrorNote, Field, Loading, Photo, useUniverses, Viewer } from "@/ui/parts";
import { Sheet, useSheetParam } from "@/ui/sheet";
import { toast } from "@/ui/toast";
import { useQuery } from "@tanstack/react-query";
import { AddCardSheet } from "./AddCard";

type Purchase = S["PurchaseOut"];

function useSummary() {
  return useQuery({ queryKey: [...keys.purchases, "summary"], queryFn: () => api<S["SummaryOut"]>("/purchases/summary") });
}

/** F-22 : liste des achats, du plus récent au plus ancien. */
export function Purchases() {
  const me = useMe();
  const [only, setOnly] = useState("all");
  const list = usePurchases(only);
  const summary = useSummary();
  const [adding, openAdd, closeAdd] = useSheetParam("ajout");
  const currency = me.data?.currency;
  const filters = [
    { key: "all", label: t("purchases.filter.all"), count: summary.data?.count },
    { key: "kept", label: t("purchases.filter.kept"), count: summary.data?.kept_count },
    { key: "sold", label: t("purchases.filter.sold"), count: summary.data?.sold_count },
  ];
  return (
    <main className="screen stack loose">
      <div className="topbar">
        <span className="kicker">{summary.data ? tn("purchases.count", summary.data.count) : " "}</span>
        <Link to="/achats/bilan" className="pill">
          <BarChart3 size={14} aria-hidden="true" />
          {t("purchases.summary")}
        </Link>
      </div>
      <div className="spread">
        <h1 className="title">{t("purchases.title")}</h1>
        <button className="icon-button accent" aria-label={t("purchases.add")} onClick={() => openAdd("1")}>
          <Camera size={20} />
        </button>
      </div>

      <div className="pills" role="group">
        {filters.map((filter) => (
          <button key={filter.key} className="pill" aria-pressed={only === filter.key} onClick={() => setOnly(filter.key)}>
            {filter.label}
            {filter.count !== undefined && <span className="count">·{filter.count}</span>}
          </button>
        ))}
      </div>

      {list.isPending && <Loading />}
      {list.isError && <ErrorNote error={list.error} retry={() => list.refetch()} />}
      {list.data?.length === 0 && <p className="empty">{t("purchases.empty")}</p>}
      <div>
        {list.data?.map((purchase) => (
          <Link key={purchase.id} to={`/achats/${purchase.id}`} className="row">
            <Photo id={purchase.photo_id} alt="" />
            <span className="grow">
              {/* RG-21 : le nom d'abord ; le code, la variante et la série en dessous. */}
              <span className="name" style={{ display: "block" }}>{purchase.name || `#${purchase.code}`}</span>
              <span className="meta" style={{ display: "block" }}>
                {purchase.code && <span className="mono">#{purchase.code}</span>}
                {purchase.code && purchase.variant && " · "}
                {purchase.variant}
              </span>
              <span className="meta" style={{ display: "block" }}>{purchase.series_name}</span>
            </span>
            <span className="mono" style={{ fontWeight: 700 }}>{money(purchase.sold ? purchase.sale_price : purchase.price, currency)}</span>
          </Link>
        ))}
      </div>
      {adding && <AddCardSheet onClose={closeAdd} />}
    </main>
  );
}

/** F-23 : fiche d'un achat. */
export function PurchaseDetail() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const me = useMe();
  const query = usePurchase(id);
  const [panel, openPanel, closePanel] = useSheetParam("panneau");
  const [viewing, setViewing] = useState(false);
  const currency = me.data?.currency;

  const follow = useApiMutation((seriesId: number) => api("/collections", { body: { series_id: seriesId } }));
  const cancelSale = useApiMutation(() => api(`/purchases/${id}/sale`, { method: "DELETE" }), (client) => { refreshOwnership(client); closePanel(); });
  const remove = useApiMutation(
    () => api(`/purchases/${id}`, { method: "DELETE" }),
    (client) => {
      client.removeQueries({ queryKey: keys.purchase(id) });
      refreshOwnership(client);
      toast(t("purchase.deleted"));
      navigate("/achats", { replace: true });
    },
  );

  if (query.isPending) return <div className="screen"><Loading /></div>;
  if (query.isError) return <div className="screen"><ErrorNote error={query.error} retry={() => query.refetch()} /></div>;
  const purchase = query.data;

  return (
    <main className="screen stack loose">
      <div className="topbar">
        <Link to="/achats" className="back">
          <ChevronLeft size={16} aria-hidden="true" />
          {t("purchases.title")}
        </Link>
        <button className="pill" onClick={() => openPanel("modifier")}>
          <Pencil size={13} aria-hidden="true" />
          {t("common.edit")}
        </button>
      </div>

      {purchase.photo_id && (
        <button onClick={() => setViewing(true)} aria-label={purchase.name} style={{ justifySelf: "center", width: "min(72%, 300px)" }}>
          <Photo id={purchase.photo_id} size="medium" alt={purchase.name} className="shot" />
        </button>
      )}

      <div className="stack" style={{ gap: 6 }}>
        <h1 className="title medium">{purchase.name || `#${purchase.code}`}</h1>
        <div className="cluster">
          {purchase.variant && <span className="chip">{purchase.variant}</span>}
          {purchase.code && <span className="mono small muted">#{purchase.code}</span>}
        </div>
        <p className="small muted">{purchase.series_name}</p>
      </div>

      <div className="tiles" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <div className="stat"><span className="muted">{t("purchase.price")}</span><strong>{money(purchase.price, currency)}</strong></div>
        <div className="stat"><span className="muted">{t("purchase.boughtOn")}</span><strong>{shortDate(purchase.bought_on)}</strong></div>
        <div className="stat"><span className="muted">{t("purchase.platform")}</span><strong style={{ fontFamily: "inherit", fontSize: 14 }}>{purchase.platform || "—"}</strong></div>
      </div>

      <section className="panel outline stack">
        <div className="spread">
          <strong>{t("purchase.sale")}</strong>
          {!purchase.sold && <span className="small muted">{t("purchase.sale.none")}</span>}
        </div>
        {purchase.sold ? (
          <>
            <div className="table" style={{ padding: 0, background: "none" }}>
              <div><span>{t("purchase.sale.price")}</span><span /><span className="mono">{money(purchase.sale_price, currency)}</span></div>
              <div><span>{t("purchase.sale.date")}</span><span /><span className="mono">{shortDate(purchase.sold_on)}</span></div>
              <div><strong>{t("purchase.sale.result")}</strong><span /><strong className="mono">{money(purchase.result, currency)}</strong></div>
            </div>
            <button className="button block" onClick={() => openPanel("annuler-vente")}>{t("purchase.sale.cancel")}</button>
          </>
        ) : (
          <button className="button primary big block" onClick={() => openPanel("vente")}>{t("purchase.sale.record")}</button>
        )}
      </section>

      {purchase.is_isolated && (
        <div className="note">
          <span className="grow">{t("purchase.isolated")}</span>
          {purchase.can_follow && purchase.series_id && (
            <button className="link" disabled={follow.isPending} onClick={() => follow.mutate(purchase.series_id!)}>
              {t("purchase.follow")}
            </button>
          )}
        </div>
      )}
      {purchase.parallel_id && purchase.card_ref_id && purchase.collection_id && (
        <div className="note">
          <span className="grow">{t("purchase.parallelOf", { code: purchase.code })}</span>
          <Link className="link" to={`/collections/${purchase.collection_id}?carte=${purchase.card_ref_id}`}>{t("common.see")}</Link>
        </div>
      )}
      <p className="small muted cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
        <Eye size={14} aria-hidden="true" style={{ flex: "none", marginTop: 2 }} />
        {purchase.sold ? t("purchase.public.sold") : t("purchase.public.kept")}
      </p>
      {purchase.note && <p>{purchase.note}</p>}

      <button className="button danger block" onClick={() => openPanel("supprimer")}>{t("common.delete")}</button>

      {panel === "vente" && <SaleSheet purchase={purchase} onClose={closePanel} />}
      {panel === "modifier" && <EditSheet purchase={purchase} onClose={closePanel} />}
      {panel === "annuler-vente" && (
        <Confirm title={t("purchase.sale.cancel")} text={t("purchase.sale.cancel.confirm")} action={t("purchase.sale.cancel")} busy={cancelSale.isPending} onConfirm={() => cancelSale.mutate(undefined)} onClose={closePanel} />
      )}
      {panel === "supprimer" && (
        <Confirm title={t("common.delete")} text={t("purchase.delete.confirm")} action={t("confirm.delete")} busy={remove.isPending} onConfirm={() => remove.mutate(undefined)} onClose={closePanel} />
      )}
      {viewing && purchase.photo_id && <Viewer id={purchase.photo_id} alt={purchase.name} onClose={() => setViewing(false)} />}
    </main>
  );
}

function SaleSheet({ purchase, onClose }: { purchase: Purchase; onClose: () => void }) {
  const [price, setPrice] = useState("");
  const [fees, setFees] = useState("");
  const [soldOn, setSoldOn] = useState(today());
  const sell = useApiMutation(
    () => api(`/purchases/${purchase.id}/sale`, { body: { price, fees: fees || null, sold_on: soldOn || null } }),
    (client) => {
      refreshOwnership(client);
      onClose();
    },
  );
  return (
    <Sheet title={t("purchase.sale.record")} onClose={onClose}>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); sell.mutate(undefined); }}>
        <Field label={t("purchase.sale.price")}>
          <input type="number" inputMode="decimal" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} required autoFocus />
        </Field>
        <Field label={`${t("purchase.sale.fees")} (${t("common.optional")})`}>
          <input type="number" inputMode="decimal" min="0" step="0.01" value={fees} onChange={(e) => setFees(e.target.value)} />
        </Field>
        <Field label={t("purchase.sale.date")}>
          <input type="date" value={soldOn} max={today()} onChange={(e) => setSoldOn(e.target.value)} />
        </Field>
        {sell.isError && <p className="error-text" role="alert">{apiErrorText(sell.error)}</p>}
        <button className="button primary big block" disabled={sell.isPending}>{t("common.save")}</button>
      </form>
    </Sheet>
  );
}

function EditSheet({ purchase, onClose }: { purchase: Purchase; onClose: () => void }) {
  const [form, setForm] = useState({
    name: purchase.name,
    variant: purchase.variant,
    price: purchase.price ?? "",
    fees: purchase.fees ?? "",
    bought_on: purchase.bought_on ?? "",
    platform: purchase.platform,
    note: purchase.note,
  });
  const set = (field: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [field]: event.target.value });
  const save = useApiMutation(
    () =>
      api(`/purchases/${purchase.id}`, {
        method: "PATCH",
        body: { ...form, price: form.price || null, fees: form.fees || null, bought_on: form.bought_on || null },
      }),
    (client) => {
      refreshOwnership(client);
      onClose();
    },
  );
  return (
    <Sheet title={t("purchase.edit")} onClose={onClose}>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); save.mutate(undefined); }}>
        <Field label={t("add.name")}><input value={form.name} onChange={set("name")} /></Field>
        <Field label={t("add.variant")}><input value={form.variant} onChange={set("variant")} /></Field>
        <Field label={t("add.price")}><input type="number" inputMode="decimal" min="0" step="0.01" value={form.price} onChange={set("price")} /></Field>
        <Field label={t("add.fees")}><input type="number" inputMode="decimal" min="0" step="0.01" value={form.fees} onChange={set("fees")} /></Field>
        <Field label={t("add.boughtOn")}><input type="date" value={form.bought_on} onChange={set("bought_on")} /></Field>
        <Field label={t("add.platform")}><input value={form.platform} onChange={set("platform")} /></Field>
        <Field label={t("card.note")}><textarea value={form.note} onChange={set("note")} rows={2} /></Field>
        {save.isError && <p className="error-text" role="alert">{apiErrorText(save.error)}</p>}
        <button className="button primary big block" disabled={save.isPending}>{t("common.save")}</button>
      </form>
    </Sheet>
  );
}

/** F-24 : bilan. */
export function Summary() {
  const me = useMe();
  const universes = useUniverses();
  const summary = useSummary();
  const currency = me.data?.currency;
  if (summary.isPending) return <div className="screen"><Loading /></div>;
  if (summary.isError) return <div className="screen"><ErrorNote error={summary.error} retry={() => summary.refetch()} /></div>;
  const data = summary.data;
  return (
    <main className="screen stack loose">
      <Link to="/achats" className="back">
        <ChevronLeft size={16} aria-hidden="true" />
        {t("purchases.title")}
      </Link>
      <h1 className="title">{t("summary.title")}</h1>
      <div className="bento">
        <div className="cell hero">
          <span>{t("summary.salesResult")}</span>
          <div>
            <strong>{money(data.sales_result, currency)}</strong>
            <div style={{ marginTop: 6 }}>{tn("summary.sold", data.sold_count)}</div>
          </div>
        </div>
        <div className="cell">
          <span className="muted">{t("summary.invested")}</span>
          <strong>{money(data.invested, currency)}</strong>
        </div>
        <div className="cell">
          <span className="muted">{tn("summary.kept", data.kept_count)}</span>
          <strong>{money(data.kept_amount, currency)}</strong>
        </div>
      </div>

      {[
        { title: t("summary.byUniverse"), rows: data.by_universe.map((row) => ({ ...row, label: universes.name(row.key as number | null) || t("summary.noUniverse") })) },
        { title: t("summary.byPlatform"), rows: data.by_platform.map((row) => ({ ...row, label: (row.key as string) || t("summary.noPlatform") })) },
      ].map(
        (block) =>
          block.rows.length > 0 && (
            <section key={block.title} className="stack">
              <h2 className="heading">{block.title}</h2>
              <div className="table">
                {block.rows.map((row) => (
                  <div key={row.label}>
                    <strong>{row.label}</strong>
                    <span className="small muted">{tn("purchases.count", row.count)}</span>
                    <strong className="mono">{money(row.amount, currency)}</strong>
                  </div>
                ))}
              </div>
            </section>
          ),
      )}
    </main>
  );
}
