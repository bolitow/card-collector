// Parcours de l'application sur un écran de 390 px (comme les captures du cahier des charges).
import { chromium } from "playwright-core";

const base = process.env.BASE_URL ?? "http://127.0.0.1:8000";
const only = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.CHROME ?? "/usr/bin/google-chrome", args: ["--no-sandbox"] });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, locale: "fr-FR", colorScheme: process.env.DARK ? "dark" : "light" });
const page = await context.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push("PAGE " + e.message));

async function shot(name, path, prepare) {
  if (only.length && !only.includes(name)) return;
  if (path) await page.goto(base + path, { waitUntil: "networkidle" });
  if (prepare) await prepare();
  await page.waitForTimeout(350);
  await page.screenshot({ path: `${name}.png` });
  console.log("ok", name);
}

await shot("01-landing", "/");
await page.goto(base + "/connexion");
await page.fill('input[type=email]', "demo@example.org");
await page.fill('input[type=password]', "demonstration");
await page.click('button.primary');
await page.waitForURL("**/collections");
await shot("02-home", "/collections");
const first = await page.evaluate(async () => (await (await fetch("/api/v1/collections")).json()).collections);
const basket = first.find((c) => c.name.includes("Basketball"));
const big = first.find((c) => c.name.includes("Flagship Football"));
await shot("03-collection", `/collections/${basket.id}`);
await shot("04-collection-wanted", `/collections/${basket.id}?type=recherchees&equipe=*`);
await shot("05-card-sheet", `/collections/${basket.id}`, async () => { await page.click(".card.owned"); await page.waitForSelector(".sheet"); });
await shot("06-purchases", "/achats");
await shot("07-add", "/achats?ajout=1");
await shot("08-purchase", "/achats", async () => { await page.click("a.row"); await page.waitForSelector(".tiles"); });
await shot("09-summary", "/achats/bilan");
await shot("10-search", "/recherche?q=brandt");
await shot("11-isolated", "/collections/isolees");
await shot("12-catalog", "/catalogue");
await shot("13-profile", "/profil");
await shot("14-sharing", "/profil/partage");
await shot("15-preview", "/profil/apercu");
if (!only.length || only.includes("perf")) {
  const t0 = Date.now();
  await page.goto(base + `/collections/${big.id}?type=tout`, { waitUntil: "commit" });
  await page.waitForSelector(".card");
  console.log("perf: collection de 4042 cartes affichée en", Date.now() - t0, "ms ; cases montées :", await page.locator(".card").count());
  await page.screenshot({ path: "16-big.png" });
}
console.log(errors.length ? "ERREURS CONSOLE:\n" + [...new Set(errors)].join("\n") : "aucune erreur console");
await browser.close();
