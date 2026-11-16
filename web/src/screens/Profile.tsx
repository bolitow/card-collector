import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, type S } from "@/api/client";
import { keys, useApiMutation, useMe } from "@/api/hooks";
import { t } from "@/i18n";
import { fileSize, shortDate } from "@/lib/format";
import { apiErrorText, ErrorNote, Field, Loading, Photo, PhotoButton, Switch } from "@/ui/parts";
import { Sheet, useSheetParam } from "@/ui/sheet";
import { toast } from "@/ui/toast";

type Me = S["MeOut"];

function useUpdateMe() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: S["MeIn"]) => api<Me>("/me", { method: "PATCH", body }),
    // L'interrupteur bascule tout de suite ; si le serveur refuse, l'état réel revient.
    onMutate: (body) => client.setQueryData<Me | null>(keys.me, (me) => (me ? ({ ...me, ...body } as Me) : me)),
    onSuccess: (me) => client.setQueryData(keys.me, me),
    onError: () => client.invalidateQueries({ queryKey: keys.me }),
  });
}

/** F-30, F-31 : paramètres du compte. */
export function Profile() {
  const me = useMe();
  const update = useUpdateMe();
  const client = useQueryClient();
  const navigate = useNavigate();
  const [panel, openPanel, closePanel] = useSheetParam("panneau");
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api<S["SessionOut"][]>("/me/sessions") });
  const exportsList = useQuery({
    queryKey: ["exports"],
    queryFn: () => api<S["JobOut"][]>("/me/exports"),
    refetchInterval: (query) => (query.state.data?.some((job) => job.status === "queued" || job.status === "running") ? 3000 : false),
  });
  const startExport = useApiMutation(() => api("/me/exports", { method: "POST" }), () => void client.invalidateQueries({ queryKey: ["exports"] }));
  const closeSession = useApiMutation((id: number) => api(`/me/sessions/${id}`, { method: "DELETE" }), () => void client.invalidateQueries({ queryKey: ["sessions"] }));
  const resend = useApiMutation(() => api("/me/verification", { method: "POST" }), () => toast(t("auth.verify.resent")));

  if (!me.data) return <div className="screen"><Loading /></div>;
  const user = me.data;
  const save = (body: S["MeIn"]) => update.mutate(body, { onSuccess: () => toast(t("profile.saved")), onError: (error) => toast(apiErrorText(error), { error: true }) });

  async function signOut() {
    await api("/auth/logout", { method: "POST" });
    client.clear();
    navigate("/", { replace: true });
  }

  return (
    <main className="screen stack loose">
      <h1 className="title">{t("profile.title")}</h1>

      {!user.email_verified && (
        <div className="note warn" role="status">
          <span className="grow">{t("auth.verify.pending")}</span>
          <button className="link" disabled={resend.isPending} onClick={() => resend.mutate(undefined)}>{t("auth.verify.resend")}</button>
        </div>
      )}

      <section className="panel stack">
        <div className="cluster" style={{ flexWrap: "nowrap" }}>
          <Photo id={user.avatar_photo_id} alt="" />
          <div className="grow">
            <strong style={{ display: "block" }}>{user.pseudo}</strong>
            <span className="small muted">{user.email}</span>
          </div>
          <PhotoButton onPhoto={(id) => save({ avatar_photo_id: id })} onError={(error) => toast(apiErrorText(error), { error: true })}>
            {t("profile.avatar")}
          </PhotoButton>
        </div>
        <button className="button block" onClick={() => openPanel("pseudo")}>{t("auth.pseudo")}</button>
        <button className="button block" onClick={() => openPanel("email")}>{t("profile.email.change")}</button>
        <button className="button block" onClick={() => openPanel("mot-de-passe")}>{t("profile.password.change")}</button>
      </section>

      <Link to="/profil/partage" className="row">
        <span className="grow">
          <span className="name" style={{ display: "block" }}>{t("sharing.title")}</span>
          <span className="meta">{user.public_profile ? `/u/${user.pseudo}` : t("sharing.off")}</span>
        </span>
        <ChevronRight size={18} aria-hidden="true" />
      </Link>

      <section className="stack">
        <h2 className="heading">{t("profile.preferences")}</h2>
        <div className="panel stack">
          <Field label={t("profile.theme")}>
            <select value={user.theme} onChange={(e) => save({ theme: e.target.value as "auto" | "light" | "dark" })}>
              <option value="auto">{t("profile.theme.auto")}</option>
              <option value="light">{t("profile.theme.light")}</option>
              <option value="dark">{t("profile.theme.dark")}</option>
            </select>
          </Field>
          <Field label={t("profile.currency")}>
            <select value={user.currency} onChange={(e) => save({ currency: e.target.value })}>
              {["EUR", "USD", "GBP", "CHF", "CAD", "JPY"].map((code) => <option key={code}>{code}</option>)}
            </select>
          </Field>
          <Field label={t("profile.language")}>
            <select value={user.locale} onChange={(e) => save({ locale: e.target.value })}>
              <option value="fr">Français</option>
            </select>
          </Field>
          <Switch label={t("profile.notify")} checked={user.notify_series_published} onChange={(checked) => save({ notify_series_published: checked })} />
        </div>
      </section>

      <section className="stack">
        <h2 className="heading">{t("profile.ai")}</h2>
        <p className="panel small">
          {user.ai_available
            ? t("profile.ai.usage", { dayUsed: user.ai.day_used, dayLimit: user.ai.day_limit, monthUsed: user.ai.month_used, monthLimit: user.ai.month_limit })
            : t("profile.ai.off")}
        </p>
      </section>

      <section className="stack">
        <h2 className="heading">{t("profile.totp")}</h2>
        <div className="panel spread">
          <span>{user.totp_enabled ? t("profile.totp.on") : t("profile.totp.off")}</span>
          {!user.totp_enabled && <button className="button" onClick={() => openPanel("totp")}>{t("profile.totp.setup")}</button>}
        </div>
      </section>

      <section className="stack">
        <h2 className="heading">{t("profile.sessions")}</h2>
        <div>
          {sessions.data?.map((session) => (
            <div key={session.id} className="row">
              <span className="grow">
                <span className="name" style={{ display: "block" }}>{session.current ? t("profile.sessions.current") : session.user_agent.slice(0, 60) || session.ip}</span>
                <span className="meta">{t("profile.sessions.lastSeen", { date: shortDate(session.last_seen_at) })} · {session.ip}</span>
              </span>
              {!session.current && <button className="button" onClick={() => closeSession.mutate(session.id)}>{t("profile.sessions.close")}</button>}
            </div>
          ))}
        </div>
      </section>

      <section className="stack">
        <h2 className="heading">{t("profile.data")}</h2>
        <div className="panel stack">
          <p className="small muted">{t("profile.export.lead")}</p>
          {exportsList.data?.slice(0, 1).map((job) =>
            job.status === "done" ? (
              <a key={job.id} className="button block" href={`/api/v1/me/exports/${job.id}/download`}>
                {t("profile.export.download", { size: fileSize(Number(job.result.bytes ?? 0)) })}
              </a>
            ) : job.status !== "failed" ? (
              <p key={job.id} className="note" role="status">{t("profile.export.pending")}</p>
            ) : null,
          )}
          <button className="button block" disabled={startExport.isPending} onClick={() => startExport.mutate(undefined)}>{t("profile.export.start")}</button>
          {startExport.isError && <p className="error-text" role="alert">{apiErrorText(startExport.error)}</p>}
        </div>
        <button className="button danger block" onClick={() => openPanel("supprimer")}>{t("profile.delete")}</button>
      </section>

      <p className="cluster small">
        <Link to="/legal/conditions">{t("landing.footer.terms")}</Link>
        <Link to="/legal/confidentialite">{t("landing.footer.privacy")}</Link>
        <Link to="/legal/mentions">{t("landing.footer.legal")}</Link>
      </p>

      {user.role === "admin" && <Link to="/admin" className="button dark block">{t("profile.admin")}</Link>}
      <button className="button block" onClick={signOut}>{t("auth.signOut")}</button>

      {panel === "pseudo" && <PseudoSheet me={user} onClose={closePanel} />}
      {panel === "email" && <EmailSheet onClose={closePanel} />}
      {panel === "mot-de-passe" && <PasswordSheet hasPassword={user.has_password} onClose={closePanel} />}
      {panel === "totp" && <TotpSheet onClose={closePanel} />}
      {panel === "supprimer" && <DeleteAccountSheet onClose={closePanel} />}
    </main>
  );
}

function PseudoSheet({ me, onClose }: { me: Me; onClose: () => void }) {
  const update = useUpdateMe();
  const [pseudo, setPseudo] = useState(me.pseudo);
  return (
    <Sheet title={t("auth.pseudo")} onClose={onClose}>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); update.mutate({ pseudo }, { onSuccess: onClose }); }}>
        <Field label={t("auth.pseudo")} hint={t("auth.pseudo.hint")} error={update.isError ? apiErrorText(update.error) : null}>
          <input value={pseudo} onChange={(e) => setPseudo(e.target.value.toLowerCase())} autoCapitalize="none" required autoFocus />
        </Field>
        <button className="button primary big block" disabled={update.isPending}>{t("common.save")}</button>
      </form>
    </Sheet>
  );
}

function EmailSheet({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = useState("");
  const change = useApiMutation(() => api("/me/email", { body: { email } }), () => { toast(t("profile.email.sent")); onClose(); });
  return (
    <Sheet title={t("profile.email.change")} onClose={onClose}>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); change.mutate(undefined); }}>
        <Field label={t("auth.email")} error={change.isError ? apiErrorText(change.error) : null}>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </Field>
        <button className="button primary big block" disabled={change.isPending}>{t("common.save")}</button>
      </form>
    </Sheet>
  );
}

function PasswordSheet({ hasPassword, onClose }: { hasPassword: boolean; onClose: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const change = useApiMutation(() => api("/me/password", { body: { current: current || null, new: next } }), () => { toast(t("profile.password.changed")); onClose(); });
  return (
    <Sheet title={t("profile.password.change")} onClose={onClose}>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); change.mutate(undefined); }}>
        {hasPassword && (
          <Field label={t("profile.password.current")}>
            <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required autoFocus />
          </Field>
        )}
        <Field label={t("profile.password.new")} hint={t("auth.password.hint")} error={change.isError ? apiErrorText(change.error) : null}>
          <input type="password" autoComplete="new-password" minLength={10} value={next} onChange={(e) => setNext(e.target.value)} required />
        </Field>
        <button className="button primary big block" disabled={change.isPending}>{t("common.save")}</button>
      </form>
    </Sheet>
  );
}

/** S-01 : double authentification (TOTP), obligatoire pour les administrateurs. */
export function TotpSheet({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const setup = useQuery({ queryKey: ["totp-setup"], queryFn: () => api<S["TotpSetupOut"]>("/me/totp/setup", { method: "POST" }), staleTime: Infinity, gcTime: 0 });
  const [code, setCode] = useState("");
  const enable = useApiMutation(() => api("/me/totp/enable", { body: { code } }), () => { void client.invalidateQueries({ queryKey: keys.me }); onClose(); });
  return (
    <Sheet title={t("profile.totp")} onClose={onClose}>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); enable.mutate(undefined); }}>
        <p className="small">{t("profile.totp.lead")}</p>
        {setup.isError && <ErrorNote error={setup.error} />}
        {setup.data && (
          <>
            <code className="panel mono" style={{ wordBreak: "break-all", userSelect: "all" }}>{setup.data.secret}</code>
            <a className="link small" href={setup.data.uri}>otpauth://</a>
          </>
        )}
        <Field label={t("auth.totp")} error={enable.isError ? apiErrorText(enable.error) : null}>
          <input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} required />
        </Field>
        <button className="button primary big block" disabled={enable.isPending}>{t("profile.totp.enable")}</button>
      </form>
    </Sheet>
  );
}

/** F-31, RG-08 : la suppression du compte demande de retaper un mot de confirmation. */
function DeleteAccountSheet({ onClose }: { onClose: () => void }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [word, setWord] = useState("");
  const remove = useApiMutation(
    () => api("/me/delete", { body: { word } }),
    () => {
      client.clear();
      toast(t("profile.delete.done"));
      navigate("/", { replace: true });
    },
  );
  return (
    <Sheet title={t("profile.delete")} onClose={onClose}>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); remove.mutate(undefined); }}>
        <p>{t("profile.delete.lead")}</p>
        <Field label={t("profile.delete.word")} error={remove.isError ? apiErrorText(remove.error) : null}>
          <input value={word} onChange={(e) => setWord(e.target.value)} autoCapitalize="characters" autoComplete="off" required />
        </Field>
        <button className="button dark big block" disabled={word.trim().toUpperCase() !== "SUPPRIMER" || remove.isPending}>{t("confirm.delete")}</button>
        <button type="button" className="button block" onClick={onClose}>{t("common.cancel")}</button>
      </form>
    </Sheet>
  );
}

/** F-42, F-44 : rien n'est public par défaut ; l'utilisateur choisit ce qu'il montre. */
export function Sharing() {
  const me = useMe();
  const update = useUpdateMe();
  const client = useQueryClient();
  const sharing = useQuery({ queryKey: keys.sharing, queryFn: () => api<S["SharingOut"]>("/me/sharing") });
  const refresh = () => void client.invalidateQueries({ queryKey: keys.sharing });
  const onError = (error: unknown) => toast(apiErrorText(error), { error: true });
  const patch = useMutation({
    mutationFn: ({ id, ...body }: S["CollectionIn"] & { id: number }) => api(`/collections/${id}`, { method: "PATCH", body }),
    onMutate: ({ id, ...body }) =>
      client.setQueryData<S["SharingOut"]>(keys.sharing, (current) =>
        current && { ...current, collections: current.collections.map((c) => (c.id === id ? ({ ...c, ...body } as typeof c) : c)) },
      ),
    onSettled: refresh,
  });
  const createLink = useApiMutation((id: number) => api(`/me/collections/${id}/links`, { method: "POST" }), refresh);
  const revoke = useApiMutation((id: number) => api(`/me/links/${id}`, { method: "DELETE" }), () => { refresh(); toast(t("sharing.link.revoked")); });

  if (sharing.isPending || !me.data) return <div className="screen"><Loading /></div>;
  if (sharing.isError) return <div className="screen"><ErrorNote error={sharing.error} /></div>;
  const data = sharing.data;
  const origin = window.location.origin;
  const copy = async (url: string) => {
    await navigator.clipboard.writeText(url);
    toast(t("common.copied"));
  };

  return (
    <main className="screen stack loose">
      <Link to="/profil" className="back">
        <ChevronLeft size={16} aria-hidden="true" />
        {t("profile.title")}
      </Link>
      <div className="stack" style={{ gap: 6 }}>
        <h1 className="title">{t("sharing.title")}</h1>
        <p className="muted">{t("sharing.lead")}</p>
      </div>

      <section className="panel stack">
        <Switch
          label={t("sharing.profile")}
          hint={me.data.public_profile ? t("sharing.profile.address", { url: `${origin}/u/${data.pseudo}` }) : undefined}
          checked={me.data.public_profile}
          onChange={(checked) => update.mutate({ public_profile: checked }, { onError })}
        />
        <Switch label={t("sharing.singles")} checked={me.data.share_singles} onChange={(checked) => update.mutate({ share_singles: checked }, { onError })} />
        <div className="cluster">
          <Link to="/profil/apercu" className="button">{t("sharing.preview")}</Link>
          {me.data.public_profile && <button className="button" onClick={() => copy(`${origin}/u/${data.pseudo}`)}>{t("sharing.link.copy")}</button>}
        </div>
      </section>

      <section className="stack">
        <h2 className="heading">{t("sharing.collections")}</h2>
        {data.collections.length === 0 && <p className="empty">{t("sharing.none")}</p>}
        {data.collections.map((collection) => (
          <div key={collection.id} className="panel stack">
            <Switch label={collection.name} checked={collection.shared} onChange={(checked) => patch.mutate({ id: collection.id, shared: checked }, { onError })} />
            <Switch label={t("sharing.photosOnly")} checked={collection.share_photos_only} onChange={(checked) => patch.mutate({ id: collection.id, share_photos_only: checked }, { onError })} />
            <Switch label={t("sharing.missing")} checked={collection.share_missing} onChange={(checked) => patch.mutate({ id: collection.id, share_missing: checked }, { onError })} />
            {collection.links.map((link) => (
              <div key={link.id} className="spread">
                <span className="mono small muted grow" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>/p/{link.token.slice(0, 10)}…</span>
                <button className="button" onClick={() => copy(`${origin}/p/${link.token}`)}>{t("sharing.link.copy")}</button>
                <button className="button danger" onClick={() => revoke.mutate(link.id)}>{t("sharing.link.revoke")}</button>
              </div>
            ))}
            <div>
              <button className="button block" disabled={createLink.isPending} onClick={() => createLink.mutate(collection.id, { onError })}>{t("sharing.link.create")}</button>
              <p className="small muted" style={{ marginTop: 6 }}>{t("sharing.link.hint")}</p>
            </div>
          </div>
        ))}
      </section>
    </main>
  );
}
