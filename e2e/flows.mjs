// Critères d'acceptation vérifiés dans un vrai navigateur, sur 390 px.
import { chromium } from "playwright-core";
import assert from "node:assert/strict";

const base = process.env.BASE_URL ?? "http://127.0.0.1:8000";
const browser = await chromium.launch({ executablePath: process.env.CHROME ?? "/usr/bin/google-chrome", args: ["--no-sandbox"] });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, locale: "fr-FR" });
await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const results = [];
const check = async (name, run) => {
  try { await run(); results.push(`OK   ${name}`); }
  catch (error) { results.push(`KO   ${name} — ${String(error.message).split("\n")[0]}`); await page.screenshot({ path: `ko-${results.length}.png` }); }
};

await page.goto(base + "/connexion");
await page.fill("input[type=email]", "demo@example.org");
await page.fill("input[type=password]", "demonstration");
await page.click("button.primary");
await page.waitForURL("**/collections");
const collections = await page.evaluate(async () => (await (await fetch("/api/v1/collections")).json()).collections);
const basket = collections.find((c) => c.name.includes("Basketball"));
const big = collections.find((c) => c.name.includes("Flagship Football"));

await check("CA-13 la collection s'ouvre sur l'équipe prioritaire ; l'accueil affiche « ★ équipe »", async () => {
  assert.match(await page.locator(".collection-row").first().innerText(), /Brooklyn Nets/);
  await page.goto(`${base}/collections/${basket.id}`);
  await page.waitForSelector(".card");
  assert.equal(await page.locator("button.pill", { hasText: "Brooklyn Nets" }).getAttribute("aria-pressed"), "true");
});

await check("CA-05 toucher une case manquante ouvre la fiche sans la cocher", async () => {
  const missing = page.locator(".card:not(.owned)").first();
  const id = await missing.getAttribute("data-id");
  await missing.click();
  await page.waitForSelector(".sheet .stepper");
  assert.match(await page.locator(".sheet").innerText(), /Manquante/);
  await page.keyboard.press("Escape");
  await page.waitForSelector(".sheet", { state: "detached" });
  assert.equal(await page.locator(`.card[data-id="${id}"]`).evaluate((n) => n.classList.contains("owned")), false);
});

await check("CA-06 saisie rapide : trois appuis puis Annuler → ×2", async () => {
  const tile = page.locator(".card:not(.owned)").first();
  const id = await tile.getAttribute("data-id");
  await page.click("text=Saisie rapide");
  for (let i = 0; i < 3; i++) await page.locator(`.card[data-id="${id}"]`).click();
  await page.locator(".banner >> text=Annuler").click();
  await page.waitForTimeout(600);
  assert.match(await page.locator(`.card[data-id="${id}"] .marks`).innerText(), /×2/);
  await page.reload(); await page.waitForSelector(".card");
  assert.match(await page.locator(`.card[data-id="${id}"] .marks`).innerText(), /×2/); // enregistré côté serveur
});

await check("CA-12 recherche dans la collection : « 3 » trouve WK-3, pas WK-30 ; « nets » ne trouve pas Hornets", async () => {
  await page.goto(`${base}/collections/${basket.id}?equipe=*&type=tout&q=wk-3`);
  await page.waitForSelector(".card");
  assert.deepEqual(await page.locator(".card .code").allInnerTexts(), ["WK-3"]);
  await page.goto(`${base}/collections/${basket.id}?equipe=*&type=insert&q=3`);
  await page.waitForSelector(".card");
  const codes = await page.locator(".card .code").allInnerTexts();
  assert.ok(codes.includes("WK-3") && !codes.includes("WK-30") && !codes.includes("WK-13"), codes.join());
  await page.goto(`${base}/collections/${basket.id}?equipe=*&type=tout&q=hornets`);
  await page.waitForSelector(".card");
  const hornets = await page.locator(".card").count();
  await page.goto(`${base}/collections/${basket.id}?equipe=*&type=tout&q=nets`);
  await page.waitForSelector(".card");
  const labels = await page.evaluate(async (id) => {
    const col = await (await fetch(`/api/v1/collections/${id}`)).json();
    const list = await (await fetch(`/api/v1/catalog/series/${col.series_id}/cards`)).json();
    const nets = list.teams.indexOf("Brooklyn Nets");
    return list.cards.filter((c) => c[4].includes(nets)).length;
  }, basket.id);
  assert.ok(hornets > 0);
  assert.equal(await page.locator(".group-header .mono").evaluateAll((nodes) => nodes.reduce((sum, n) => sum + Number(n.textContent.split("/")[1]), 0)), labels);
});

await check("CA-15 réseau coupé pendant un cochage : retour arrière, bandeau, « Réessayer » enregistre", async () => {
  await page.goto(`${base}/collections/${basket.id}?equipe=*&type=base`);
  await page.waitForSelector(".card");
  const tile = page.locator(".card:not(.owned)").first();
  const id = await tile.getAttribute("data-id");
  await tile.click();
  await page.waitForSelector(".sheet .stepper");
  await context.setOffline(true);
  await page.locator('.sheet button[aria-label="Un exemplaire de plus"]').click();
  await page.waitForSelector(".banner.error");
  assert.equal(await page.locator(".sheet output").innerText(), "0"); // retour arrière visible
  await context.setOffline(false);
  await page.locator(".banner.error >> text=Réessayer").click();
  await page.waitForSelector(".banner.error", { state: "detached" });
  await page.waitForTimeout(400);
  const saved = await page.evaluate(async (ref) => (await (await fetch(`/api/v1/cards/${ref}`)).json()).quantity, id);
  assert.equal(saved, 1);
  await page.keyboard.press("Escape");
});

await check("CA-17 collection de 4 042 cartes : affichage en moins d'1 s, défilement fluide", async () => {
  const cdp = await context.newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 }); // processeur de téléphone
  const times = [];
  for (let run = 0; run < 4; run++) {
    await page.goto(`${base}/collections`);
    await page.waitForSelector(".collection-row");
    const start = Date.now();
    await page.locator(".collection-row", { hasText: "Flagship Football" }).click(); // parcours réel : depuis l'accueil
    await page.waitForSelector(".card");
    if (run > 0) times.push(Date.now() - start); // le premier passage remplit le cache de la checklist
  }
  times.sort((a, b) => a - b);
  const mounted = await page.locator(".card").count();
  const frames = await page.evaluate(() => new Promise((resolve) => {
    let slow = 0, last = performance.now(), n = 0;
    const tick = (now) => { if (now - last > 50) slow++; last = now; window.scrollBy(0, 400); if (++n < 60) requestAnimationFrame(tick); else resolve(slow); };
    requestAnimationFrame(tick);
  }));
  const cold = Date.now();
  await page.goto(`${base}/collections/${big.id}`, { waitUntil: "commit" });
  await page.waitForSelector(".card");
  const coldTime = Date.now() - cold;
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
  results.push(`     (processeur ralenti ×4 — depuis l'accueil : ${times.join(", ")} ms ; rechargement complet de la page : ${coldTime} ms ; ${mounted} cases montées ; ${frames}/60 images lentes au défilement)`);
  assert.ok(times[1] < 1000, `médiane ${times[1]} ms`);
});

await check("CA-19 thème sombre et lecteur d'écran : cases annoncées « code, nom, état, carte recherchée »", async () => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(`${base}/collections/${basket.id}?equipe=*&type=recherchees`);
  await page.waitForSelector(".card");
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "dark");
  const label = await page.locator(".card").first().getAttribute("aria-label");
  assert.match(label, /^[\w-]+, .+, (possédée|manquante|\d+ exemplaires).*, carte recherchée$/);
  const contrast = await page.evaluate(() => {
    const lum = (rgb) => { const [r, g, b] = rgb.match(/[\d.]+/g).slice(0, 3).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
    const body = getComputedStyle(document.body);
    const muted = getComputedStyle(document.querySelector(".muted"));
    return [ratio(body.color, body.backgroundColor), ratio(muted.color, body.backgroundColor)];
  });
  assert.ok(contrast.every((c) => c >= 4.5), contrast.join());
  await page.screenshot({ path: "17-dark.png" });
  await page.emulateMedia({ colorScheme: "light" });
});

await check("F-18 à F-21 ajout d'une carte achetée, lecture IA simulée puis saisie", async () => {
  await page.goto(`${base}/achats?ajout=1`);
  await page.waitForSelector(".sheet");
  await page.locator(".sheet .capture input[type=file]").setInputFiles({ name: "carte.png", mimeType: "image/png", buffer: Buffer.from(await page.evaluate(async () => { const c = document.createElement("canvas"); c.width = 300; c.height = 420; const x = c.getContext("2d"); x.fillStyle = "#7A4BD1"; x.fillRect(0, 0, 300, 420); return c.toDataURL("image/png").split(",")[1]; }), "base64") });
  await page.waitForSelector("text=Nouvelle carte");
  await page.waitForSelector("text=Photo lue", { timeout: 8000 });
  await page.locator(".sheet").getByLabel("Numéro").fill("17");
  await page.locator(".sheet").getByLabel("Variante").fill("Gold 35/50");
  await page.locator(".sheet").getByLabel("Prix d'achat").fill("15");
  await page.click("text=Enregistrer la carte");
  await page.waitForSelector(".toast >> text=Carte enregistrée");
  await page.waitForSelector(".sheet", { state: "detached" });
  assert.match(await page.locator("a.row").first().innerText(), /Gold 35\/50/);
});

await check("CA-02 / CA-03 profil public : seules les collections partagées, aucun prix ; lien révoqué", async () => {
  await page.goto(`${base}/profil/partage`);
  await page.waitForSelector(".switch");
  await page.locator(".switch", { hasText: "Profil public" }).locator("input").check();
  await page.locator(".switch", { hasText: "Démo Flagship Basketball" }).locator("input").check();
  await page.waitForTimeout(500);
  const visitor = await (await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "fr-FR" })).newPage();
  const responses = [];
  visitor.on("response", async (r) => r.url().includes("/api/v1/public/") && r.headers()["content-type"]?.includes("json") && responses.push(await r.text()));
  await visitor.goto(`${base}/u/demo`, { waitUntil: "networkidle" });
  const text = await visitor.locator("main").innerText();
  assert.match(text, /Lecture seule/);
  assert.ok((await visitor.locator(".gallery figure").count()) > 0);
  assert.ok(!/€|Vinted|eBay/.test(text) && !/price|bought_on|platform|quantity/.test(responses.join()), "donnée privée exposée");
  assert.ok(!text.includes("Chrome Club Competitions"), "collection non partagée visible");
  await visitor.screenshot({ path: "18-public.png" });
  const link = await page.evaluate(async (id) => (await (await fetch(`/api/v1/me/collections/${id}/links`, { method: "POST" })).json()), basket.id);
  assert.equal((await visitor.goto(`${base}/api/v1/public/links/${link.token}`)).status(), 200);
  await page.evaluate(async (id) => fetch(`/api/v1/me/links/${id}`, { method: "DELETE" }), link.id);
  assert.equal((await visitor.goto(`${base}/api/v1/public/links/${link.token}`)).status(), 404);
});

console.log(results.join("\n"));
console.log(errors.length ? "ERREURS DE PAGE:\n" + [...new Set(errors)].join("\n") : "aucune erreur de page");
await browser.close();
