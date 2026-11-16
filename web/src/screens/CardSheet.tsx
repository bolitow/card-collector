import { Camera, Flame, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { api, type S } from "@/api/client";
import { refreshOwnership, useApiMutation, useCard, useCardWriter } from "@/api/hooks";
import { t, tn } from "@/i18n";
import { money, today } from "@/lib/format";
import { apiErrorText, Confirm, ErrorNote, Field, Loading, Photo, PhotoButton, Viewer } from "@/ui/parts";
import { Sheet, useSheetParam } from "@/ui/sheet";
import { toast } from "@/ui/toast";

function stateLabel(card: S["CardOut"]): string {
  const live = card.parallels.filter((p) => !p.sold).length;
  if (card.quantity === 0) return live > 0 ? t("card.state.parallel") : t("card.state.missing");
  if (card.quantity === 1) return t("card.state.one");
  return tn("card.state.many", card.quantity - 1, { count: card.quantity, doubles: card.quantity - 1 });
}

/**
 * Fiche d'une carte (F-13 à F-15), ouverte par le paramètre d'adresse `carte` depuis n'importe quel
 * écran : collection, recherche, cartes isolées.
 */
export function CardSheet() {
  const [value, , close] = useSheetParam("carte");
  const [parallelParam, openParallel, closeParallel] = useSheetParam("parallele");
  const [reporting, setReporting] = useState(false);
  const [viewing, setViewing] = useState<string | null>(null);
  const location = useLocation();
  const refId = value ? Number(value) : null;
  const query = useCard(refId);
  const card = query.data;
  const write = useCardWriter(card?.collection_id ?? null);
  const follow = useApiMutation(() => api("/collections", { body: { series_id: card!.series_id } }));

  if (refId === null) return null;
  if (!card) {
    return (
      <Sheet title={t("common.loading")} onClose={close}>
        {query.isError ? <ErrorNote error={query.error} retry={() => query.refetch()} /> : <Loading rows={3} />}
      </Sheet>
    );
  }
  if (reporting) return <ReportSheet cardRefId={card.card_ref_id} onClose={() => setReporting(false)} />;
  if (parallelParam) {
    return <ParallelSheet card={card} parallelId={parallelParam === "nouveau" ? null : Number(parallelParam)} onClose={closeParallel} />;
  }

  const photoId = card.photo_id ?? card.purchase_photo_id;
  const inCollection = location.pathname === `/collections/${card.collection_id}`;
  const playerName = card.name.replace(/ RC$/, "").split(" / ")[0];

  return (
    <Sheet title={t("card.title", { code: card.code })} onClose={close}>
      <div className="stack">
        <div className="cluster" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
          {photoId ? (
            <button onClick={() => setViewing(photoId)} aria-label={card.name}>
              <Photo id={photoId} size="medium" alt="" className="thumb" />
            </button>
          ) : (
            <Photo id={null} alt="" />
          )}
          <div className="grow stack" style={{ gap: 6 }}>
            <strong>{card.name}</strong>
            <span className="small muted">
              {card.series_name} · {card.group}
              {card.teams.length > 0 && ` · ${card.teams.join(" / ")}`}
            </span>
            {!card.photo_id && card.purchase_photo_id && <span className="small muted">{t("card.photo.fromPurchase")}</span>}
            <PhotoButton onPhoto={(id) => write(card.card_ref_id, { photo_id: id })} onError={(error) => toast(apiErrorText(error), { error: true })}>
              <Camera size={16} aria-hidden="true" />
              {card.photo_id ? t("card.photo.change") : t("card.photo.add")}
            </PhotoButton>
          </div>
        </div>

        {card.chase_reason !== null && (
          <div className="note">
            <Flame size={16} fill="currentColor" aria-hidden="true" />
            <span>
              <strong>{t("card.wanted.editorial")}</strong>
              {card.chase_reason && ` — ${card.chase_reason}`}
            </span>
          </div>
        )}

        <div>
          <span className="label">{t("card.copies")}</span>
          <div className="stepper" style={{ margin: "6px 0" }}>
            <button aria-label={t("card.less")} disabled={card.quantity === 0} onClick={() => write(card.card_ref_id, { quantity: card.quantity - 1 })}>
              −
            </button>
            <output aria-live="polite">{card.quantity}</output>
            <button aria-label={t("card.more")} disabled={card.quantity >= 999} onClick={() => write(card.card_ref_id, { quantity: card.quantity + 1 })}>
              +
            </button>
          </div>
          <span className="small muted">{stateLabel(card)}</span>
        </div>

        <div>
          <span className="label">{t("card.parallels")}</span>
          <div style={{ margin: "6px 0" }}>
            {card.parallels.map((parallel) => (
              <button key={parallel.id} className="row" onClick={() => openParallel(String(parallel.id))}>
                <Photo id={parallel.photo_id} alt="" />
                <span className="grow name">{parallel.name}</span>
                {parallel.sold ? <span className="chip outline">{t("parallel.sold")}</span> : parallel.purchase && <span className="mono small">{money(parallel.purchase.price)}</span>}
              </button>
            ))}
          </div>
          <button className="button block" onClick={() => openParallel("nouveau")}>
            <Plus size={16} aria-hidden="true" />
            {t("card.parallels.add")}
          </button>
          <p className="small muted" style={{ marginTop: 6 }}>{t("card.parallels.hint")}</p>
        </div>

        <button className="button block" aria-pressed={card.wanted} onClick={() => write(card.card_ref_id, { wanted: !card.wanted })}>
          <Flame size={16} fill={card.wanted ? "currentColor" : "none"} aria-hidden="true" />
          {card.wanted ? t("card.wanted.unmark") : t("card.wanted.mark")}
        </button>

        <Field label={t("card.note")}>
          <textarea
            key={card.card_ref_id}
            defaultValue={card.note}
            rows={2}
            onBlur={(event) => event.target.value !== card.note && write(card.card_ref_id, { note: event.target.value })}
          />
        </Field>

        <button className="button primary big block" onClick={close}>
          {t("common.done")}
        </button>

        {card.collection_id === null && (
          <button className="button block" disabled={follow.isPending} onClick={() => follow.mutate(undefined)}>
            {t("card.followToTrack")}
          </button>
        )}
        {card.collection_id !== null && !inCollection && (
          <Link className="button block" to={`/collections/${card.collection_id}?carte=${card.card_ref_id}`}>
            {t("card.seeInCollection")}
          </Link>
        )}
        <div className="spread">
          {/* Ajout : toutes les cartes d'un joueur, toutes séries confondues. */}
          <Link className="link small" to={`/recherche?q=${encodeURIComponent(playerName)}&onglet=catalogue`}>
            {t("card.allOfPlayer", { name: playerName })}
          </Link>
          <button className="link small" onClick={() => setReporting(true)}>
            {t("card.reportError")}
          </button>
        </div>
      </div>
      {viewing && <Viewer id={viewing} alt={card.name} onClose={() => setViewing(null)} />}
    </Sheet>
  );
}

/** Panneau d'un parallèle (F-16, F-17). */
function ParallelSheet(props: { card: S["CardOut"]; parallelId: number | null; onClose: () => void }) {
  const { card, parallelId, onClose } = props;
  const parallel = card.parallels.find((p) => p.id === parallelId) ?? null;
  const [name, setName] = useState(parallel?.name ?? "");
  const [photoId, setPhotoId] = useState<string | null>(parallel?.photo_id ?? null);
  const [confirming, setConfirming] = useState(false);
  const [pricing, setPricing] = useState(false);
  const [price, setPrice] = useState("");
  const [boughtOn, setBoughtOn] = useState(today());
  const [platform, setPlatform] = useState("");

  const done = (client: Parameters<typeof refreshOwnership>[0]) => {
    refreshOwnership(client);
    onClose();
  };
  const save = useApiMutation(
    () =>
      parallel
        ? api(`/parallels/${parallel.id}`, { method: "PATCH", body: { name, photo_id: photoId } })
        : api(`/cards/${card.card_ref_id}/parallels`, { body: { name, photo_id: photoId } }),
    done,
  );
  const remove = useApiMutation(() => api(`/parallels/${parallel!.id}`, { method: "DELETE" }), done);
  const addPrice = useApiMutation(
    () => api(`/parallels/${parallel!.id}/purchase`, { body: { price, bought_on: boughtOn || null, platform } }),
    done,
  );

  if (confirming) {
    return <Confirm title={t("parallel.delete")} text={t("confirm.sure")} action={t("confirm.delete")} busy={remove.isPending} onConfirm={() => remove.mutate(undefined)} onClose={() => setConfirming(false)} />;
  }
  return (
    <Sheet title={parallel ? t("parallel.title") : t("parallel.title.new")} onClose={onClose}>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); save.mutate(undefined); }}>
        <div className="cluster" style={{ flexWrap: "nowrap" }}>
          <Photo id={photoId} size="medium" alt="" />
          <PhotoButton onPhoto={setPhotoId} onError={(error) => toast(apiErrorText(error), { error: true })}>
            <Camera size={16} aria-hidden="true" />
            {photoId ? t("card.photo.change") : t("card.photo.add")}
          </PhotoButton>
        </div>
        <Field label={t("parallel.name")}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("parallel.name.placeholder")} required maxLength={80} autoFocus={!parallel} />
        </Field>
        {card.official_parallels.length > 0 && (
          // F-16 : parallèles officiels de la série en suggestion ; la saisie libre reste possible.
          <div>
            <span className="label">{t("parallel.suggestions")}</span>
            <div className="cluster" style={{ marginTop: 6 }}>
              {card.official_parallels.map((suggestion) => (
                <button type="button" key={suggestion} className="pill" onClick={() => setName(suggestion)}>
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {parallel && (
          <div className="panel outline stack">
            <span className="label">{t("parallel.purchase")}</span>
            {parallel.purchase ? (
              <Link className="button block" to={`/achats/${parallel.purchase.id}`}>
                {t("parallel.purchase.see", { price: money(parallel.purchase.price) })}
              </Link>
            ) : pricing ? (
              <>
                <Field label={t("add.price")}>
                  <input type="number" inputMode="decimal" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} autoFocus />
                </Field>
                <Field label={t("add.boughtOn")}>
                  <input type="date" value={boughtOn} onChange={(e) => setBoughtOn(e.target.value)} />
                </Field>
                <Field label={t("add.platform")}>
                  <input value={platform} onChange={(e) => setPlatform(e.target.value)} />
                </Field>
                <button type="button" className="button dark block" disabled={!price || addPrice.isPending} onClick={() => addPrice.mutate(undefined)}>
                  {t("common.save")}
                </button>
              </>
            ) : (
              <button type="button" className="button block" onClick={() => setPricing(true)}>
                {t("parallel.purchase.add")}
              </button>
            )}
          </div>
        )}

        {(save.isError || addPrice.isError) && <p className="error-text" role="alert">{apiErrorText(save.error ?? addPrice.error)}</p>}
        <button className="button primary big block" disabled={save.isPending}>{t("common.save")}</button>
        {parallel && (
          <button type="button" className="button danger block" onClick={() => setConfirming(true)}>
            {t("parallel.delete")}
          </button>
        )}
      </form>
    </Sheet>
  );
}

/** « Signaler une erreur » sur une référence (RG-03) ou un contenu public (F-45). */
export function ReportSheet(props: { cardRefId?: number; pseudo?: string; photoId?: string; onClose: () => void }) {
  const [message, setMessage] = useState("");
  const content = props.cardRefId === undefined;
  const send = useApiMutation(
    () =>
      api("/reports", {
        body: { kind: content ? "content" : "catalog", message, card_ref_id: props.cardRefId, pseudo: props.pseudo, photo_id: props.photoId },
      }),
    () => {
      toast(t("report.sent"));
      props.onClose();
    },
  );
  return (
    <Sheet title={content ? t("common.report") : t("report.title")} onClose={props.onClose}>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); send.mutate(undefined); }}>
        <Field label={content ? t("report.content.text") : t("report.text")}>
          <textarea value={message} onChange={(e) => setMessage(e.target.value)} required minLength={3} maxLength={2000} rows={4} autoFocus />
        </Field>
        {send.isError && <p className="error-text" role="alert">{apiErrorText(send.error)}</p>}
        <button className="button primary big block" disabled={send.isPending}>{t("report.submit")}</button>
      </form>
    </Sheet>
  );
}
