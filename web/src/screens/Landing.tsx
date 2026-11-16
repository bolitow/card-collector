import { Link } from "react-router-dom";

import { t } from "@/i18n";

// Cases de démonstration : noms inventés, mêmes formes que l'écran d'une collection.
const DEMO = [
  ["83", "N. Carrel", true], ["90", "T. Vasseur", false], ["135", "M. Okoro", true],
  ["151", "C. Lindqvist", true], ["167", "D. Maro", false], ["238", "J. Petit", true],
  ["261", "M. Brandt", true], ["283", "E. Sorel", false], ["301", "A. Diallo", true],
] as const;

/** Page d'accueil publique (section 11, nouvel écran). */
export function Landing() {
  return (
    <div className="landing">
      <header className="spread">
        <span className="heading">{t("app.name")}</span>
        <Link to="/connexion" className="button">{t("nav.signIn")}</Link>
      </header>

      <main>
        <section className="landing-hero">
          <div className="stack loose">
            <h1>{t("landing.title")}</h1>
            <p>{t("landing.lead")}</p>
            <div className="cluster">
              <Link to="/inscription" className="button dark big">{t("landing.start")}</Link>
              <Link to="/catalogue" className="button big">{t("landing.browse")}</Link>
            </div>
          </div>

          <div className="stage" aria-hidden="true">
            <div className="mock">
              <div className="spread" style={{ alignItems: "flex-end" }}>
                <strong style={{ font: "780 22px/1.05 var(--font-title)", letterSpacing: "-0.02em" }}>Flagship<br />Basketball</strong>
                <span style={{ textAlign: "right" }}>
                  <strong className="mono" style={{ display: "block", fontSize: 18, color: "#55700a" }}>66 %</strong>
                  <span className="mono" style={{ fontSize: 11, color: "#5f6355" }}>6 / 9</span>
                </span>
              </div>
              <div className="bar" style={{ background: "#e9ebe2" }}><span style={{ width: "66%", background: "#55700a" }} /></div>
              <div className="cards" style={{ marginTop: 14, gridTemplateColumns: "repeat(3, 1fr)" }}>
                {DEMO.map(([code, name, owned]) => (
                  <div key={code} className={`card${owned ? " owned" : ""}`} style={owned ? undefined : { borderColor: "#cfd3c4" }}>
                    <span className="code">{code}</span>
                    <span className="label" style={{ color: owned ? "#14160f" : "#5f6355" }}>{name}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="points">
          {([1, 2, 3] as const).map((n) => (
            <div key={n}>
              <h2>{t(`landing.point${n}.title`)}</h2>
              <p className="muted">{t(`landing.point${n}.text`)}</p>
            </div>
          ))}
        </section>
      </main>

      <footer className="cluster small muted" style={{ marginTop: 56 }}>
        <Link to="/legal/conditions">{t("landing.footer.terms")}</Link>
        <Link to="/legal/confidentialite">{t("landing.footer.privacy")}</Link>
        <Link to="/legal/mentions">{t("landing.footer.legal")}</Link>
      </footer>
    </div>
  );
}
