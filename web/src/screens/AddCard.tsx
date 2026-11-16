import { Camera, Image as ImageIcon, Info } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api, ApiError, type S } from "@/api/client";
import { refreshOwnership, useApiMutation, useMe, useSeriesList } from "@/api/hooks";
import { t } from "@/i18n";
import { today } from "@/lib/format";
import { apiErrorText, Field, Photo, PhotoButton, useUniverses } from "@/ui/parts";
import { Sheet } from "@/ui/sheet";
import { toast } from "@/ui/toast";

type Reading = "idle" | "reading" | "read" | "empty" | "failed";
type SeriesChoice = { id: number | null; name: string; followed: boolean };

/**
 * Ajout d'une carte par photo (F-18 à F-21). L'IA remplit les champs vides et propose des
 * références du catalogue ; rien n'est enregistré avant l'appui sur « Enregistrer » (RG-19).
 */
export function AddCardSheet(props: { onClose: () => void; series?: SeriesChoice }) {
  const me = useMe();
  const universes = useUniverses();
  const [step, setStep] = useState<"source" | "form">("source");
  const [photoId, setPhotoId] = useState<string | null>(null);
  const [reading, setReading] = useState<Reading>("idle");
  const [readError, setReadError] = useState("");
  const [candidates, setCandidates] = useState<S["CandidateOut"][]>([]);
  const cancelled = useRef(false);
  const saved = useRef(false);

  const [series, setSeries] = useState<SeriesChoice>(props.series ?? { id: null, name: "", followed: false });
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [variant, setVariant] = useState("");
  const [kind, setKind] = useState<"collection" | "purchase">("purchase");
  const [quantity, setQuantity] = useState(1);
  const [asParallel, setAsParallel] = useState<boolean | null>(null);
  const [price, setPrice] = useState("");
  const [fees, setFees] = useState("");
  const [boughtOn, setBoughtOn] = useState(today());
  const [platform, setPlatform] = useState("");
  const [universeId, setUniverseId] = useState<number | null>(null);
  const [problem, setProblem] = useState("");
  const [platforms, setPlatforms] = useState<string[]>([]);

  useEffect(() => {
    void api<string[]>("/purchases/platforms").then(setPlatforms, () => {});
  }, []);

  // F-21 : une photo envoyée puis abandonnée ne reste pas dans le stockage.
  const photoRef = useRef<string | null>(null);
  photoRef.current = photoId;
  useEffect(
    () => () => {
      if (photoRef.current && !saved.current) void api(`/photos/${photoRef.current}`, { method: "DELETE" }).catch(() => {});
    },
    [],
  );

  async function read(id: string) {
    if (!me.data?.ai_available) return;
    cancelled.current = false;
    setReading("reading");
    try {
      const result = await api<S["ReadingOut"]>("/ai/read-card", { body: { photo_id: id } });
      if (cancelled.current) return;
      const nothing = !result.series && !result.code && !result.name && !result.variant;
      setReading(nothing ? "empty" : "read");
      // L'IA ne remplit que les champs vides : ce que l'utilisateur a déjà saisi est conservé.
      const best = result.candidates[0];
      setSeries((current) => (current.name ? current : best ? { id: best.series_id, name: best.series_name, followed: false } : { id: null, name: result.series, followed: false }));
      setCode((current) => current || result.code);
      setName((current) => current || best?.name || result.name);
      setVariant((current) => current || (result.variant === "Base" ? "" : result.variant));
      setCandidates(result.candidates.filter((c) => c.card_ref_id !== null));
    } catch (error) {
      if (cancelled.current) return;
      setReading("failed"); // quota atteint, IA indisponible ou réponse inexploitable : saisie manuelle
      setReadError(apiErrorText(error));
    }
  }

  function onPhoto(id: string) {
    setPhotoId(id);
    setStep("form");
    void read(id);
  }

  const save = useApiMutation(
    async () => {
      if (kind === "collection") {
        const ref = await api<S["CandidateOut"]>(`/catalog/series/${series.id}/ref`, { params: { code } });
        if (variant.trim()) {
          await api(`/cards/${ref.card_ref_id}/parallels`, { body: { name: variant.trim(), photo_id: photoId } });
        } else {
          const current = await api<S["CardOut"]>(`/cards/${ref.card_ref_id}`);
          const body: S["CardStateIn"] = { quantity: Math.min(current.quantity + quantity, 999) };
          if (photoId && !current.photo_id) body.photo_id = photoId;
          await api(`/cards/${ref.card_ref_id}`, { method: "PUT", body });
        }
        return;
      }
      await api("/purchases", {
        body: {
          series_id: series.id,
          series_name: series.id ? null : series.name,
          universe_id: series.id ? null : universeId,
          code: code || null,
          name: name || null,
          variant: variant || null,
          as_parallel: asParallel,
          photo_id: photoId,
          price: price || null,
          fees: fees || null,
          bought_on: boughtOn || null,
          platform: platform || null,
        },
      });
    },
    (client) => {
      saved.current = true;
      refreshOwnership(client);
      toast(t("add.saved"));
      props.onClose();
    },
  );

  function submit(event: React.FormEvent) {
    event.preventDefault();
    // F-21 : série obligatoire ; numéro obligatoire pour une carte de collection.
    if (!series.name.trim()) return setProblem(t("error.series_required"));
    if (kind === "collection" && !series.id) return setProblem(t("add.catalogRequired"));
    if (kind === "collection" && !code.trim()) return setProblem(t("add.codeRequired"));
    setProblem("");
    save.mutate(undefined);
  }

  if (step === "source") {
    return (
      <Sheet title={t("add.title")} onClose={props.onClose}>
        <div className="stack">
          <p className="small muted">{t("add.lead")}</p>
          <PhotoButton capture className="capture" onPhoto={onPhoto} onError={(error) => toast(apiErrorText(error), { error: true })}>
            <Camera size={30} aria-hidden="true" />
            {t("add.camera")}
          </PhotoButton>
          <PhotoButton className="button block big" onPhoto={onPhoto} onError={(error) => toast(apiErrorText(error), { error: true })}>
            <ImageIcon size={16} aria-hidden="true" />
            {t("add.library")}
          </PhotoButton>
          <button className="link" onClick={() => setStep("form")}>
            {t("add.manual")}
          </button>
          <div className="note">
            <Info size={16} aria-hidden="true" />
            <span>{t("add.isolatedNote")}</span>
          </div>
        </div>
      </Sheet>
    );
  }

  const saveError =
    save.error instanceof ApiError && save.error.code === "card_not_found" ? t("add.unknownCode") : save.isError ? apiErrorText(save.error) : "";

  return (
    <Sheet title={t("add.form.title")} onClose={props.onClose}>
      <form className="stack" onSubmit={submit} noValidate>
        {photoId && (
          <div className="cluster" style={{ flexWrap: "nowrap" }} aria-live="polite">
            <Photo id={photoId} size="medium" alt="" />
            <div className="grow small">
              {reading === "reading" && (
                <span className="spread">
                  {t("add.reading")}
                  <button type="button" className="link" onClick={() => { cancelled.current = true; setReading("idle"); }}>
                    {t("add.reading.skip")}
                  </button>
                </span>
              )}
              {reading === "read" && t("add.read.ok")}
              {reading === "empty" && (
                <span className="spread">
                  {t("add.read.empty")}
                  <button type="button" className="link" onClick={() => read(photoId)}>
                    {t("common.retry")}
                  </button>
                </span>
              )}
              {reading === "failed" && readError}
            </div>
          </div>
        )}

        {candidates.length > 0 && (
          <div>
            <span className="label">{t("add.read.candidates")}</span>
            {candidates.map((candidate) => (
              <button
                type="button"
                key={`${candidate.series_id}-${candidate.card_ref_id}`}
                className="row"
                style={{ marginTop: 6 }}
                aria-pressed={series.id === candidate.series_id && code === candidate.code}
                onClick={() => {
                  setSeries({ id: candidate.series_id, name: candidate.series_name, followed: false });
                  setCode(candidate.code);
                  setName(candidate.name);
                }}
              >
                <span className="grow">
                  <span className="name">{candidate.name}</span>
                  <span className="meta">
                    <span className="mono">#{candidate.code}</span> · {candidate.group} · {candidate.series_name}
                  </span>
                </span>
              </button>
            ))}
          </div>
        )}

        <SeriesField value={series} onChange={setSeries} />
        <div className="cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
          <Field label={t("add.code")}>
            <input value={code} onChange={(e) => setCode(e.target.value)} autoCapitalize="characters" autoCorrect="off" />
          </Field>
          <div className="grow">
            <Field label={t("add.variant")}>
              <input value={variant} onChange={(e) => setVariant(e.target.value)} placeholder={t("add.variant.placeholder")} />
            </Field>
          </div>
        </div>
        <Field label={t("add.name")}>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>

        <div>
          <span className="label">{t("add.kind")}</span>
          <div className="segmented" style={{ marginTop: 6 }}>
            <button type="button" aria-pressed={kind === "collection"} onClick={() => setKind("collection")}>
              {t("add.kind.collection")}
            </button>
            <button type="button" aria-pressed={kind === "purchase"} onClick={() => setKind("purchase")}>
              {t("add.kind.purchase")}
            </button>
          </div>
        </div>

        {kind === "collection" ? (
          !variant.trim() && (
            <div>
              <span className="label">{t("add.quantity")}</span>
              <div className="stepper" style={{ marginTop: 6 }}>
                <button type="button" aria-label={t("card.less")} onClick={() => setQuantity(Math.max(1, quantity - 1))}>−</button>
                <output>{quantity}</output>
                <button type="button" aria-label={t("card.more")} onClick={() => setQuantity(Math.min(999, quantity + 1))}>+</button>
              </div>
            </div>
          )
        ) : (
          <>
            <div className="cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
              <div className="grow">
                <Field label={t("add.price")}>
                  <input type="number" inputMode="decimal" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} />
                </Field>
              </div>
              <div className="grow">
                <Field label={t("add.boughtOn")}>
                  <input type="date" value={boughtOn} max={today()} onChange={(e) => setBoughtOn(e.target.value)} />
                </Field>
              </div>
            </div>
            <div className="cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
              <div className="grow">
                <Field label={t("add.platform")}>
                  <input value={platform} onChange={(e) => setPlatform(e.target.value)} list="platforms" />
                  <datalist id="platforms">
                    {platforms.map((p) => (
                      <option key={p} value={p} />
                    ))}
                  </datalist>
                </Field>
              </div>
              <Field label={`${t("add.fees")} (${t("common.optional")})`}>
                <input type="number" inputMode="decimal" min="0" step="0.01" value={fees} onChange={(e) => setFees(e.target.value)} style={{ width: 110 }} />
              </Field>
            </div>
            {series.id !== null && variant.trim() && (
              // F-20 : choix « Parallèle / Carte de base » ; sans choix, la variante décide (RG-09).
              <div>
                <span className="label">{t("add.asParallel")}</span>
                <div className="segmented" style={{ marginTop: 6 }}>
                  <button type="button" aria-pressed={asParallel === true} onClick={() => setAsParallel(asParallel === true ? null : true)}>
                    {t("add.asParallel.yes")}
                  </button>
                  <button type="button" aria-pressed={asParallel === false} onClick={() => setAsParallel(asParallel === false ? null : false)}>
                    {t("add.asParallel.no")}
                  </button>
                </div>
              </div>
            )}
            {series.id === null && (
              <div>
                <span className="label">{t("add.universe")}</span>
                <div className="cluster" style={{ marginTop: 6 }}>
                  {universes.list.map((u) => (
                    <button type="button" key={u.id} className="pill" aria-pressed={universeId === u.id} onClick={() => setUniverseId(universeId === u.id ? null : u.id)}>
                      {u.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {(problem || saveError) && <p className="error-text" role="alert">{problem || saveError}</p>}
        <button className="button primary big block" disabled={save.isPending}>{t("add.submit")}</button>
      </form>
    </Sheet>
  );
}

/** Série : recherche dans le catalogue, ou nom libre quand la série n'y est pas (F-20, RG-10). */
function SeriesField({ value, onChange }: { value: SeriesChoice; onChange: (value: SeriesChoice) => void }) {
  const [open, setOpen] = useState(false);
  const [debounced, setDebounced] = useState(value.name);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value.name), 200);
    return () => window.clearTimeout(timer);
  }, [value.name]);
  const results = useSeriesList({ q: debounced });
  const options = open && value.id === null && debounced.trim().length >= 2 ? (results.data ?? []).slice(0, 6) : [];
  return (
    <div>
      <Field label={t("add.series")}>
        <input
          value={value.name}
          placeholder={t("add.series.placeholder")}
          autoComplete="off"
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setOpen(true);
            onChange({ id: null, name: e.target.value, followed: false });
          }}
        />
      </Field>
      {options.length > 0 && (
        <div style={{ marginTop: 6 }}>
          {options.map((option) => (
            <button
              type="button"
              key={option.id}
              className="row"
              onClick={() => {
                onChange({ id: option.id, name: option.name, followed: option.followed ?? false });
                setOpen(false);
              }}
            >
              <span className="grow name">{option.name}</span>
              {option.followed && <span className="chip">{t("catalog.followed")}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
