import { Camera, X } from "lucide-react";
import { type CSSProperties, type ReactNode, useEffect, useState } from "react";

import { api, ApiError, photoUrl, type S } from "@/api/client";
import { useCatalogIndex } from "@/api/hooks";
import { errorText, t } from "@/i18n";
import { shrinkPhoto } from "@/lib/image";
import { Sheet } from "./sheet";

export function apiErrorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return t("error.network");
    return errorText(error.code === "generic" && error.status === 404 ? "not_found" : error.code);
  }
  return t("error.generic");
}

export function ErrorNote({ error, retry }: { error: unknown; retry?: () => void }) {
  return (
    <div className="banner" role="alert">
      <span>{apiErrorText(error)}</span>
      {retry && (
        <button className="link" onClick={retry}>
          {t("common.retry")}
        </button>
      )}
    </div>
  );
}

export function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-label={t("common.loading")}>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="skeleton" />
      ))}
    </div>
  );
}

export function Field(props: { label: string; hint?: string; error?: string | null; children: ReactNode }) {
  return (
    <label className="field">
      <span>{props.label}</span>
      {props.children}
      {props.hint && !props.error && <small className="hint">{props.hint}</small>}
      {props.error && (
        <small className="error" role="alert">
          {props.error}
        </small>
      )}
    </label>
  );
}

/** Univers du catalogue, avec leur couleur selon le thème (section 11). */
export function useUniverses() {
  const { data } = useCatalogIndex();
  const dark = document.documentElement.dataset.theme === "dark";
  const byId = new Map((data?.universes ?? []).map((universe) => [universe.id, universe]));
  return {
    list: data?.universes ?? [],
    name: (id: number | null | undefined) => (id ? (byId.get(id)?.name ?? "") : ""),
    style: (id: number | null | undefined): CSSProperties => {
      const universe = id ? byId.get(id) : undefined;
      if (!universe) return {};
      return { "--universe": dark ? universe.color_dark : universe.color_light } as CSSProperties;
    },
  };
}

export function Photo(props: {
  id: string | null | undefined;
  size?: "thumb" | "medium" | "large";
  alt: string;
  shareToken?: string | null;
  className?: string;
}) {
  const { id, size = "thumb", alt, shareToken, className = "thumb" } = props;
  if (!id) {
    return (
      <span className={className} aria-hidden="true">
        <Camera size={16} />
      </span>
    );
  }
  return <img className={className} src={photoUrl(id, size, shareToken)} alt={alt} loading="lazy" decoding="async" />;
}

/** Photo en plein écran (F-13, F-43). */
export function Viewer(props: { id: string; alt: string; shareToken?: string | null; onClose: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && props.onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });
  return (
    <div className="viewer" role="dialog" aria-modal="true" aria-label={props.alt} onClick={props.onClose}>
      <img src={photoUrl(props.id, "large", props.shareToken)} alt={props.alt} />
      <button className="icon-button" aria-label={t("common.close")} onClick={props.onClose} autoFocus>
        <X size={18} />
      </button>
    </div>
  );
}

export async function uploadPhoto(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", await shrinkPhoto(file), "photo.jpg");
  return (await api<S["PhotoOut"]>("/photos", { form })).id;
}

/** Bouton qui ouvre l'appareil photo ou la photothèque, puis envoie la photo. */
export function PhotoButton(props: {
  onPhoto: (id: string) => void;
  onError: (error: unknown) => void;
  capture?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <label className={props.className ?? "button"} aria-busy={busy}>
      <input
        type="file"
        accept="image/*"
        capture={props.capture ? "environment" : undefined}
        className="sr-only"
        disabled={busy}
        onChange={async (event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (!file) return;
          setBusy(true);
          try {
            props.onPhoto(await uploadPhoto(file));
          } catch (error) {
            props.onError(error);
          } finally {
            setBusy(false);
          }
        }}
      />
      {busy ? t("common.loading") : props.children}
    </label>
  );
}

/** RG-08 : confirmation en deux temps pour toute suppression. */
export function Confirm(props: {
  title: string;
  text: string;
  action: string;
  onConfirm: () => void;
  onClose: () => void;
  busy?: boolean;
}) {
  return (
    <Sheet title={props.title} onClose={props.onClose}>
      <div className="stack">
        <p>{props.text}</p>
        <button className="button dark block big" onClick={props.onConfirm} disabled={props.busy}>
          {props.action}
        </button>
        <button className="button block" onClick={props.onClose}>
          {t("common.cancel")}
        </button>
      </div>
    </Sheet>
  );
}

export function Switch(props: { label: string; checked: boolean; onChange: (checked: boolean) => void; hint?: string }) {
  // L'interrupteur bascule à l'appui ; il reprend l'état réel dès que celui-ci change.
  const [shown, setShown] = useState(props.checked);
  const [known, setKnown] = useState(props.checked);
  if (known !== props.checked) {
    setKnown(props.checked);
    setShown(props.checked);
  }
  return (
    <label className="switch">
      <span>
        {props.label}
        {props.hint && (
          <small className="muted" style={{ display: "block" }}>
            {props.hint}
          </small>
        )}
      </span>
      <input
        type="checkbox"
        role="switch"
        checked={shown}
        onChange={(event) => {
          setShown(event.target.checked);
          props.onChange(event.target.checked);
        }}
      />
    </label>
  );
}

export function SearchBox(props: { value: string; onChange: (value: string) => void; placeholder: string; autoFocus?: boolean }) {
  return (
    <div className="search">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" strokeLinecap="round" />
      </svg>
      <input
        type="search"
        inputMode="search"
        enterKeyHint="search"
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        value={props.value}
        placeholder={props.placeholder}
        aria-label={props.placeholder}
        autoFocus={props.autoFocus}
        onChange={(event) => props.onChange(event.target.value)}
      />
      {props.value && (
        <button className="clear" aria-label={t("common.clear")} onClick={() => props.onChange("")}>
          <X size={16} />
        </button>
      )}
    </div>
  );
}
