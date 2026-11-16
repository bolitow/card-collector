import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, ApiError } from "@/api/client";
import { keys } from "@/api/hooks";
import { t } from "@/i18n";
import { apiErrorText, Field } from "@/ui/parts";

function AuthPage(props: { title: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <main className="screen bare stack loose" style={{ maxWidth: 440, paddingTop: 40 }}>
      <Link to="/" className="heading" style={{ textDecoration: "none" }}>{t("app.name")}</Link>
      <h1 className="title">{props.title}</h1>
      {props.children}
      {props.footer && <p className="small">{props.footer}</p>}
    </main>
  );
}

/** Après connexion : retour à la page demandée, si elle appartient à l'application. */
function useAfterSignIn() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  return async () => {
    await client.invalidateQueries({ queryKey: keys.me });
    client.clear();
    const next = params.get("suite");
    navigate(next && next.startsWith("/") && !next.startsWith("//") ? next : "/collections", { replace: true });
  };
}

export function SignIn() {
  const done = useAfterSignIn();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [needTotp, setNeedTotp] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/login", { body: { email, password, totp: totp || null } });
      await done();
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "totp_required") setNeedTotp(true);
      setError(apiErrorText(failure));
    } finally {
      setBusy(false);
    }
  }

  async function sendLink() {
    if (!email) return setError(t("auth.email"));
    setError("");
    try {
      await api("/auth/magic-link", { body: { email } });
      setInfo(t("auth.linkSent"));
    } catch (failure) {
      setError(apiErrorText(failure));
    }
  }

  const suite = params.get("suite");
  return (
    <AuthPage
      title={t("auth.signIn.title")}
      footer={<>{t("auth.signIn.noAccount")} <Link to={`/inscription${suite ? `?suite=${encodeURIComponent(suite)}` : ""}`} className="link">{t("auth.signUp.title")}</Link></>}
    >
      <form className="stack" onSubmit={submit}>
        <Field label={t("auth.email")}>
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </Field>
        <Field label={t("auth.password")}>
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        {needTotp && (
          <Field label={t("auth.totp")}>
            <input inputMode="numeric" autoComplete="one-time-code" value={totp} onChange={(e) => setTotp(e.target.value)} autoFocus />
          </Field>
        )}
        {error && <p className="error-text" role="alert">{error}</p>}
        {info && <p className="note" role="status">{info}</p>}
        <button className="button primary big block" disabled={busy}>{t("auth.signIn.submit")}</button>
        <div className="spread">
          <Link to="/mot-de-passe-oublie" className="link small">{t("auth.signIn.forgot")}</Link>
          <button type="button" className="link small" onClick={sendLink}>{t("auth.signIn.byLink")}</button>
        </div>
      </form>
    </AuthPage>
  );
}

export function SignUp() {
  const done = useAfterSignIn();
  const [form, setForm] = useState({ email: "", password: "", pseudo: "" });
  const [terms, setTerms] = useState(false);
  const [age, setAge] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/register", { body: { ...form, accept_terms: terms, age_confirmed: age } });
      await done();
    } catch (failure) {
      setError(apiErrorText(failure));
    } finally {
      setBusy(false);
    }
  }
  const set = (field: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [field]: event.target.value });

  return (
    <AuthPage title={t("auth.signUp.title")} footer={<>{t("auth.signUp.hasAccount")} <Link to="/connexion" className="link">{t("auth.signIn.submit")}</Link></>}>
      <form className="stack" onSubmit={submit}>
        <Field label={t("auth.email")}>
          <input type="email" autoComplete="email" value={form.email} onChange={set("email")} required autoFocus />
        </Field>
        <Field label={t("auth.password")} hint={t("auth.password.hint")}>
          <input type="password" autoComplete="new-password" minLength={10} value={form.password} onChange={set("password")} required />
        </Field>
        <Field label={t("auth.pseudo")} hint={t("auth.pseudo.hint")}>
          <input autoComplete="username" autoCapitalize="none" pattern="[a-z0-9][a-z0-9_\-]{2,23}" value={form.pseudo} onChange={(e) => setForm({ ...form, pseudo: e.target.value.toLowerCase() })} required />
        </Field>
        {/* F-29 : CGU, politique de confidentialité, confirmation de l'âge. */}
        <div>
          <label className="check">
            <input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} />
            <span>
              {t("auth.terms")}{" "}
              <Link to="/legal/conditions" target="_blank" className="small">{t("landing.footer.terms")}</Link>
              {" · "}
              <Link to="/legal/confidentialite" target="_blank" className="small">{t("landing.footer.privacy")}</Link>
            </span>
          </label>
          <label className="check">
            <input type="checkbox" checked={age} onChange={(e) => setAge(e.target.checked)} />
            <span>{t("auth.age")}</span>
          </label>
        </div>
        {error && <p className="error-text" role="alert">{error}</p>}
        <button className="button primary big block" disabled={busy}>{t("auth.signUp.submit")}</button>
      </form>
    </AuthPage>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/auth/forgot-password", { body: { email } });
      setSent(true);
    } catch (failure) {
      setError(apiErrorText(failure));
    }
  }
  return (
    <AuthPage title={t("auth.forgot.title")} footer={<Link to="/connexion" className="link">{t("auth.signIn.submit")}</Link>}>
      {sent ? (
        <p className="note" role="status">{t("auth.linkSent")}</p>
      ) : (
        <form className="stack" onSubmit={submit}>
          <p>{t("auth.forgot.text")}</p>
          <Field label={t("auth.email")}>
            <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
          </Field>
          {error && <p className="error-text" role="alert">{error}</p>}
          <button className="button primary big block">{t("auth.forgot.submit")}</button>
        </form>
      )}
    </AuthPage>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/auth/reset-password", { body: { token: params.get("token") ?? "", password } });
      setDone(true);
      window.setTimeout(() => navigate("/connexion", { replace: true }), 1500);
    } catch (failure) {
      setError(apiErrorText(failure));
    }
  }
  return (
    <AuthPage title={t("auth.reset.title")}>
      {done ? (
        <p className="note" role="status">{t("auth.reset.done")}</p>
      ) : (
        <form className="stack" onSubmit={submit}>
          <Field label={t("profile.password.new")} hint={t("auth.password.hint")}>
            <input type="password" autoComplete="new-password" minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus />
          </Field>
          {error && <p className="error-text" role="alert">{error}</p>}
          <button className="button primary big block">{t("auth.reset.submit")}</button>
        </form>
      )}
    </AuthPage>
  );
}

/** Lien reçu par e-mail : le jeton est consommé une seule fois, à l'ouverture de la page. */
function useTokenOnce(path: string, onSuccess: () => void) {
  const [params] = useSearchParams();
  const [error, setError] = useState("");
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api(path, { body: { token: params.get("token") ?? "" } }).then(onSuccess, (failure) => setError(apiErrorText(failure)));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return error;
}

export function VerifyEmail() {
  const client = useQueryClient();
  const [ok, setOk] = useState(false);
  const error = useTokenOnce("/auth/verify-email", () => {
    setOk(true);
    void client.invalidateQueries({ queryKey: keys.me });
  });
  return (
    <AuthPage title={t("auth.email")} footer={<Link to="/collections" className="link">{t("nav.collections")}</Link>}>
      {ok && <p className="note" role="status">{t("auth.verify.ok")}</p>}
      {error && <p className="error-text" role="alert">{error}</p>}
    </AuthPage>
  );
}

export function MagicLink() {
  const done = useAfterSignIn();
  const error = useTokenOnce("/auth/magic-link/consume", () => void done());
  return (
    <AuthPage title={t("auth.magic.title")} footer={error ? <Link to="/connexion" className="link">{t("auth.signIn.submit")}</Link> : undefined}>
      {error && <p className="error-text" role="alert">{error}</p>}
    </AuthPage>
  );
}
