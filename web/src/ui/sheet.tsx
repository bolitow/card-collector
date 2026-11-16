import { X } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { t } from "@/i18n";

/**
 * Panneau montant du bas sur téléphone, fenêtre sur ordinateur (F-02).
 * Échap ou un appui à l'extérieur le ferme ; le focus y reste tant qu'il est ouvert.
 */
export function Sheet(props: { title: string; onClose: () => void; children: ReactNode; large?: boolean }) {
  const { title, onClose, children, large } = props;
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const node = panel.current!;
    node.focus();
    const scroll = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onKey(event: KeyboardEvent) {
      // Seul le panneau du dessus réagit.
      const sheets = document.querySelectorAll(".sheet");
      if (sheets[sheets.length - 1] !== node) return;
      if (event.key === "Escape") {
        event.stopPropagation();
        close.current();
      }
      if (event.key === "Tab") {
        const focusable = node.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex="0"]',
        );
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = scroll;
      previous?.focus?.();
    };
  }, []);

  return (
    <div className="sheet-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div
        ref={panel}
        className={`sheet${large ? " large" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <div className="sheet-header">
          <h2 className="heading">{title}</h2>
          <button className="icon-button" onClick={onClose} aria-label={t("common.close")}>
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/**
 * Paramètre d'adresse qui pilote un panneau : chaque panneau a ainsi sa propre adresse (F-03),
 * le bouton retour du navigateur le ferme, et fermer un panneau ouvert depuis une fiche ramène
 * à cette fiche.
 */
export function useSheetParam(name: string): [string | null, (value: string) => void, () => void] {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const value = params.get(name);

  const open = (next: string) => {
    const search = new URLSearchParams(params);
    search.set(name, next);
    navigate({ search: `?${search}` }, { state: { sheet: true } });
  };
  const close = () => {
    if ((location.state as { sheet?: boolean } | null)?.sheet) {
      navigate(-1);
    } else {
      const search = new URLSearchParams(params);
      search.delete(name);
      setParams(search, { replace: true });
    }
  };
  return [value, open, close];
}
