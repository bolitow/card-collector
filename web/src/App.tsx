import { Library, Search, ShoppingBag, SquareStack, User } from "lucide-react";
import { lazy, Suspense, useEffect, useSyncExternalStore } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { isOutdated } from "./api/client";
import { useFailedWrites, useMe } from "./api/hooks";
import { setLocale, t, tn } from "./i18n";
import { ForgotPassword, MagicLink, ResetPassword, SignIn, SignUp, VerifyEmail } from "./screens/Auth";
import { CardSheet } from "./screens/CardSheet";
import { Catalog, SeriesPage } from "./screens/Catalog";
import { CollectionScreen } from "./screens/Collection";
import { Home } from "./screens/Home";
import { Isolated } from "./screens/Isolated";
import { Landing } from "./screens/Landing";
import { Legal } from "./screens/Legal";
import { Profile, Sharing } from "./screens/Profile";
import { PublicLink, PublicProfile, SharingPreview } from "./screens/Public";
import { PurchaseDetail, Purchases, Summary } from "./screens/Purchases";
import { SearchScreen } from "./screens/SearchScreen";
import { Loading } from "./ui/parts";
import { Toasts } from "./ui/toast";

const Admin = lazy(() => import("./screens/admin/Admin")); // chargé seulement pour les administrateurs

function useOnline(): boolean {
  return useSyncExternalStore(
    (listener) => {
      window.addEventListener("online", listener);
      window.addEventListener("offline", listener);
      return () => {
        window.removeEventListener("online", listener);
        window.removeEventListener("offline", listener);
      };
    },
    () => navigator.onLine,
  );
}

/** Thème clair ou sombre selon l'appareil, réglable par l'utilisateur (section 11). */
function useTheme(preference: string | undefined): void {
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = preference === "dark" || (preference !== "light" && media.matches);
      document.documentElement.dataset.theme = dark ? "dark" : "light";
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [preference]);
}

/** Navigation (F-01) : barre en bas sur téléphone, colonne latérale sur ordinateur. */
function Shell() {
  const failures = useFailedWrites();
  const online = useOnline();
  const location = useLocation();

  useEffect(() => {
    // Le serveur a été mis à jour : on recharge à la navigation suivante (8.3).
    if (isOutdated()) window.location.reload();
  }, [location.pathname]);

  const items = [
    { to: "/collections", label: t("nav.collections"), icon: SquareStack },
    { to: "/catalogue", label: t("nav.catalog"), icon: Library },
    { to: "/recherche", label: t("nav.search"), icon: Search },
    { to: "/achats", label: t("nav.purchases"), icon: ShoppingBag },
    { to: "/profil", label: t("nav.profile"), icon: User },
  ];
  return (
    <div className="app with-nav">
      {!online && (
        <div className="screen bare" style={{ paddingBottom: 0 }}>
          <div className="banner">{t("common.offline")}</div>
        </div>
      )}
      {failures.count > 0 && (
        <div className="banner error pinned" role="alert">
          <span>{tn("sync.failed", failures.count)}</span>
          <button className="link" onClick={failures.retry}>
            {t("common.retry")}
          </button>
        </div>
      )}
      <Outlet />
      <CardSheet />
      <nav className="nav" aria-label={t("app.name")}>
        <span className="brand">{t("app.name")}</span>
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to}>
            <Icon size={20} aria-hidden="true" />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

function RequireAccount() {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <div className="screen"><Loading /></div>;
  if (!me.data) return <Navigate to={`/connexion?suite=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  return <Outlet />;
}

export function App() {
  const me = useMe();
  useTheme(me.data?.theme);
  useEffect(() => setLocale(me.data?.locale ?? "fr"), [me.data?.locale]);
  const signedIn = Boolean(me.data);

  return (
    <>
      <Routes>
        <Route path="/" element={me.isPending ? null : signedIn ? <Navigate to="/collections" replace /> : <Landing />} />
        <Route path="/connexion" element={<SignIn />} />
        <Route path="/connexion/lien" element={<MagicLink />} />
        <Route path="/inscription" element={<SignUp />} />
        <Route path="/mot-de-passe-oublie" element={<ForgotPassword />} />
        <Route path="/reinitialiser" element={<ResetPassword />} />
        <Route path="/verifier" element={<VerifyEmail />} />
        <Route path="/legal/:page" element={<Legal />} />
        <Route path="/u/:pseudo" element={<PublicProfile />} />
        <Route path="/p/:token" element={<PublicLink />} />

        {/* Le catalogue est ouvert aux visiteurs (F-32) ; connecté, il garde la navigation. */}
        <Route element={signedIn ? <Shell /> : <Outlet />}>
          <Route path="/catalogue" element={<Catalog />} />
          <Route path="/catalogue/:id" element={<SeriesPage />} />
        </Route>

        <Route element={<RequireAccount />}>
          <Route element={<Shell />}>
            <Route path="/collections" element={<Home />} />
            <Route path="/collections/isolees" element={<Isolated />} />
            <Route path="/collections/:id" element={<CollectionScreen />} />
            <Route path="/recherche" element={<SearchScreen />} />
            <Route path="/achats" element={<Purchases />} />
            <Route path="/achats/bilan" element={<Summary />} />
            <Route path="/achats/:id" element={<PurchaseDetail />} />
            <Route path="/profil" element={<Profile />} />
            <Route path="/profil/partage" element={<Sharing />} />
            <Route path="/profil/apercu" element={<SharingPreview />} />
            <Route
              path="/admin/*"
              element={
                <Suspense fallback={<div className="screen"><Loading /></div>}>
                  <Admin />
                </Suspense>
              }
            />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Toasts />
    </>
  );
}
