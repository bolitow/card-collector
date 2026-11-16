"""Import et mise à jour d'une checklist (F-36 à F-39, RG-04).

Le brouillon est un document JSON (annexe D) que l'administrateur relit et corrige. Rien n'entre au
catalogue avant `publish` (RG-19).

    {"groups": [{"name", "kind", "prefix", "cards": [{"code", "names", "teams", "rookie", "ref_id"}]}]}
"""

import re
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError, Conflict, NotFound
from app.models import (
    GROUP_KINDS,
    CardRef,
    CardRefTeam,
    ChecklistImport,
    Publisher,
    Purchase,
    Series,
    SeriesGroup,
    SeriesRequest,
    SeriesRequestVote,
    SeriesVersion,
    Team,
    Universe,
    User,
    UserCard,
    UserParallel,
)
from app.rules import codes
from app.rules.search import fold
from app.security import now
from app.services import ai, catalog, checklist_text, jobs, mail

BLOCKING = {"code_invalide", "code_en_double", "groupe_sans_nom", "type_inconnu"}


# ----------------------------------------------------------- brouillon


def card_name(card: dict[str, Any]) -> str:
    """Convention 9.2 : « A / B » pour plusieurs joueurs, « RC » pour un rookie."""
    name = " / ".join(n.strip() for n in card.get("names", []) if n.strip())
    return f"{name} RC" if card.get("rookie") and name else name


def effective_code(group: dict[str, Any], card: dict[str, Any]) -> str:
    """Convention 9.2 : le code est préfixé quand la sous-série reprend les numéros de la base."""
    code = codes.normalize_code(card["code"])
    prefix = (group.get("prefix") or "").strip().upper()
    return codes.normalize_code(f"{prefix}-{code}") if prefix else code


def suggest_prefix(name: str) -> str:
    """Initiales de la sous-série : « Golden Mirror Variations » → « GMV »."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", name) if fold(w) not in {"of", "the", "and", "de", "du"}]
    return "".join(w[0] for w in words).upper()[:6]


def normalize_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Nettoie un brouillon reçu de l'IA ou de l'interface. Ne corrige pas le fond."""
    groups = []
    for group in draft.get("groups", []):
        cards = []
        for card in group.get("cards", []):
            cards.append(
                {
                    "code": str(card.get("code", "")).strip().lstrip("#"),
                    "names": [str(n).strip() for n in card.get("names", []) if str(n).strip()],
                    "teams": [str(t).strip() for t in card.get("teams", []) if str(t).strip()],
                    "rookie": bool(card.get("rookie")),
                    "ref_id": card.get("ref_id"),
                }
            )
        groups.append(
            {
                "name": str(group.get("name", "")).strip(),
                "kind": group.get("kind", "base"),
                "prefix": str(group.get("prefix") or "").strip().upper(),
                "cards": cards,
            }
        )
    return {"groups": groups}


def find_anomalies(draft: dict[str, Any]) -> list[dict[str, Any]]:
    """Anomalies détectées (F-36, étape 2) : calculées par le code, pas par le modèle.

    Types : code_invalide, code_en_double (bloquants) ; hors_base, nom_different, coquille,
    groupe_vide (à traiter ou à accepter).
    """
    anomalies: list[dict[str, Any]] = []

    def report(kind: str, group: int, detail: str, proposal: str = "", code: str = "") -> None:
        anomalies.append({"type": kind, "group": group, "code": code, "detail": detail, "proposal": proposal})

    seen: dict[str, tuple[int, str]] = {}  # clé de code → (sous-série, nom)
    base_names: dict[str, str] = {}
    for index, group in enumerate(draft["groups"]):
        if not group["name"]:
            report("groupe_sans_nom", index, "Sous-série sans nom")
        if group["kind"] not in GROUP_KINDS:
            report("type_inconnu", index, f"Type « {group['kind']} » inconnu")
        if not group["cards"]:
            report(
                "groupe_vide",
                index,
                f"« {group['name']} » ne contient aucune carte",
                "Supprimer la sous-série",
            )
        collisions = 0
        for card in group["cards"]:
            try:
                code = effective_code(group, card)
            except codes.InvalidCode as error:
                report("code_invalide", index, str(error), code=card["code"])
                continue
            key = codes.code_key(code)
            name = card_name(card)
            if key in seen:
                other, _ = seen[key]
                collisions += other != index
                if other == index:
                    report(
                        "code_en_double",
                        index,
                        f"{code} apparaît deux fois dans « {group['name']} »",
                        code=code,
                    )
            else:
                seen[key] = (index, name)
            if group["kind"] == "base" and not group["prefix"]:
                base_names.setdefault(key, name)
            for value in card["names"]:
                if len(value) > 3 and value.isupper():
                    report("coquille", index, f"« {value} » en majuscules", value.title(), code)
        if collisions:
            other_names = sorted(
                {
                    draft["groups"][seen[codes.code_key(effective_code(group, c))][0]]["name"]
                    for c in group["cards"]
                }
                - {group["name"]}
            )
            report(
                "code_en_double",
                index,
                f"{collisions} code(s) de « {group['name']} » existent déjà dans {', '.join(other_names)}",
                f"Préfixer : {suggest_prefix(group['name'])}-",
            )

    # Une variation reprend le numéro d'une carte de base : même numéro, même joueur.
    for index, group in enumerate(draft["groups"]):
        if group["kind"] != "special":
            continue
        for card in group["cards"]:
            try:
                key = codes.code_key(card["code"])
            except codes.InvalidCode:
                continue
            if not key.isdigit() or not base_names:
                continue
            if key not in base_names:
                report(
                    "hors_base",
                    index,
                    f"Le n° {card['code']} ne correspond à aucune carte de base",
                    code=card["code"],
                )
            elif fold(base_names[key]) != fold(card_name(card)):
                report(
                    "nom_different",
                    index,
                    f"N° {card['code']} : « {card_name(card)} » ici, « {base_names[key]} » dans la base",
                    base_names[key],
                    card["code"],
                )
    return anomalies


def counters(draft: dict[str, Any]) -> dict[str, Any]:
    by_kind = Counter()
    for group in draft["groups"]:
        by_kind[group["kind"]] += len(group["cards"])
    return {"groups": len(draft["groups"]), "cards": sum(by_kind.values()), "by_kind": dict(by_kind)}


# ------------------------------------------------------- étapes 1 et 2


def create(db: Session, admin: User, data: dict[str, Any], pdf: bytes | None = None) -> ChecklistImport:
    """Étape 1 : source (PDF de l'éditeur ou texte collé), univers et éditeur."""
    if db.get(Universe, data["universe_id"]) is None or db.get(Publisher, data["publisher_id"]) is None:
        raise NotFound(code="universe_or_publisher_not_found")
    text = checklist_text.extract_pdf_text(pdf) if pdf else data.get("text", "")
    if not text.strip():
        raise AppError(code="import_empty")
    record = ChecklistImport(
        admin_id=admin.id,
        series_id=data.get("series_id"),
        universe_id=data["universe_id"],
        publisher_id=data["publisher_id"],
        series_name=data.get("series_name", "").strip(),
        season=data.get("season", "").strip(),
        source=data.get("source", "").strip(),
        source_text=text,
        use_ai=data.get("use_ai", True),
        status="analyzing",
    )
    db.add(record)
    db.flush()
    jobs.enqueue(db, "analyze_import", {"import_id": record.id}, admin.id)
    return record


def from_series(db: Session, admin: User, series: Series) -> ChecklistImport:
    """F-38 : ouvre une série publiée en brouillon ; chaque carte garde son identifiant (RG-04)."""
    refs = db.scalars(
        select(CardRef)
        .where(CardRef.series_id == series.id, CardRef.status == "active")
        .order_by(CardRef.position)
    ).all()
    by_group: dict[int, list[dict]] = defaultdict(list)
    for ref in refs:
        rookie = ref.rookie
        name = ref.name[:-3] if rookie and ref.name.endswith(" RC") else ref.name
        prefix = ref.group.prefix
        code = ref.code[len(prefix) + 1 :] if prefix and ref.code.startswith(prefix + "-") else ref.code
        by_group[ref.group_id].append(
            {
                "code": code,
                "names": [n for n in name.split(" / ") if n],
                "teams": [t.name for t in ref.teams],
                "rookie": rookie,
                "ref_id": ref.id,
            }
        )
    draft = {
        "groups": [
            {"name": g.name, "kind": g.kind, "prefix": g.prefix, "cards": by_group.get(g.id, [])}
            for g in series.groups
        ]
    }
    record = ChecklistImport(
        admin_id=admin.id,
        series_id=series.id,
        universe_id=series.universe_id,
        publisher_id=series.publisher_id,
        series_name=series.name,
        season=series.season,
        source=series.source,
        status="review",
        draft=draft,
    )
    db.add(record)
    db.flush()
    return record


@jobs.handler("analyze_import")
def analyze(db: Session, job) -> dict:
    """Étape 2 : analyse du texte, par l'IA quand elle est disponible, sinon par lecture simple."""
    record = db.get(ChecklistImport, job.payload["import_id"])
    admin = db.get(User, record.admin_id)
    provider = ai.get_provider() if record.use_ai else None
    groups: list[dict[str, Any]] = []
    used_ai = False
    if provider and admin:
        parts = checklist_text.chunks(record.source_text)
        try:
            for index, (context, text) in enumerate(parts):
                chunk = ai.run(
                    db,
                    admin,
                    "import_checklist",
                    provider.import_model,
                    lambda text=text, context=context: provider.parse_checklist(text, context),
                    metered=False,
                )
                for group in chunk.groupes:
                    cards = [
                        {"code": c.code, "names": c.noms, "teams": c.equipes, "rookie": c.rookie}
                        for c in group.cartes
                    ]
                    # Une sous-série coupée entre deux extraits se poursuit.
                    if groups and groups[-1]["name"] == group.nom:
                        groups[-1]["cards"].extend(cards)
                    else:
                        groups.append({"name": group.nom, "kind": group.type, "cards": cards})
                job.progress = (index + 1) * 100 // len(parts)
                db.commit()
            used_ai = True
        except AppError:
            groups = []  # IA-04 : on retombe sur la lecture simple
    if not used_ai:
        groups = checklist_text.parse_plain(record.source_text)

    record = db.get(ChecklistImport, job.payload["import_id"])
    record.draft = normalize_draft({"groups": groups})
    record.status = "review"
    return {"used_ai": used_ai, **counters(record.draft)}


# ------------------------------------------------- étape 4 : publication


def check_series_name(db: Session, record: ChecklistImport, publisher: Publisher) -> list[str]:
    """F-39 : convention 9.2 — marque + produit + sport ou compétition + saison."""
    problems = []
    name = record.series_name
    if not name:
        return ["Le nom de la série est obligatoire."]
    if not fold(name).startswith(fold(publisher.name)) and fold(publisher.name) not in fold(name):
        problems.append(f"Le nom devrait commencer par la marque « {publisher.name} ».")
    if record.season and not name.endswith(record.season):
        problems.append(f"Le nom devrait se terminer par la saison « {record.season} ».")
    if record.season and not re.fullmatch(r"\d{4}(/\d{2})?", record.season):
        problems.append("La saison s'écrit « 2026 » ou « 2025/26 ».")

    def squash(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", fold(value))

    for other_id, other_name in db.execute(select(Series.id, Series.name)):
        if other_id != record.series_id and squash(other_name) == squash(name):
            problems.append(f"Une série presque identique existe déjà : « {other_name} ».")
    return problems


def _plan(db: Session, record: ChecklistImport) -> dict[str, Any]:
    """Compare le brouillon à la série publiée. Chaque référence existante garde son identifiant."""
    existing: dict[int, CardRef] = {}
    if record.series_id:
        existing = {r.id: r for r in db.scalars(select(CardRef).where(CardRef.series_id == record.series_id))}
    by_key = {r.code_key: r for r in existing.values()}

    rows, matched = [], set()
    for group_index, group in enumerate(record.draft["groups"]):
        for position, card in enumerate(group["cards"]):
            code = effective_code(group, card)
            ref = existing.get(card.get("ref_id") or -1) or by_key.get(codes.code_key(code))
            if ref and ref.id in matched:
                ref = None
            if ref:
                matched.add(ref.id)
            rows.append({"group": group_index, "position": position, "code": code, "card": card, "ref": ref})

    gone = [r for r in existing.values() if r.id not in matched and r.status == "active"]
    owners = dict(
        db.execute(
            select(UserCard.card_ref_id, func.count())
            .where(UserCard.card_ref_id.in_([r.id for r in gone]), UserCard.owned)
            .group_by(UserCard.card_ref_id)
        ).all()
    )
    return {"rows": rows, "gone": gone, "owners": owners}


def diff(db: Session, record: ChecklistImport) -> dict[str, Any]:
    """F-38 : changements montrés avant publication."""
    plan = _plan(db, record)
    groups = record.draft["groups"]
    added, renamed, recoded, moved = [], [], [], []
    for row in plan["rows"]:
        ref, name = row["ref"], card_name(row["card"])
        if ref is None:
            added.append({"code": row["code"], "name": name, "group": groups[row["group"]]["name"]})
            continue
        if ref.name != name:
            renamed.append({"code": row["code"], "before": ref.name, "after": name})
        if ref.code != row["code"]:
            recoded.append({"before": ref.code, "after": row["code"], "name": name})
        if ref.group.name != groups[row["group"]]["name"]:
            moved.append(
                {"code": row["code"], "before": ref.group.name, "after": groups[row["group"]]["name"]}
            )
    removed = [{"code": r.code, "name": r.name, "owners": plan["owners"].get(r.id, 0)} for r in plan["gone"]]
    return {
        "is_update": record.series_id is not None,
        "added": added[:200],
        "renamed": renamed[:200],
        "recoded": recoded[:200],
        "moved": moved[:200],
        "removed": removed[:200],
        "counts": {
            "added": len(added),
            "renamed": len(renamed),
            "recoded": len(recoded),
            "moved": len(moved),
            "removed": len(removed),
            "unchanged": len(plan["rows"]) - len(added),
        },
    }


def publish(db: Session, admin: User, record: ChecklistImport) -> Series:
    """Étape 4. RG-04 : aucun identifiant de référence ne change ; une référence possédée ou achetée
    qui disparaît de la checklist est masquée, jamais supprimée."""
    if record.status not in ("review", "published"):
        raise Conflict(code="import_not_ready")
    record.draft = normalize_draft(record.draft)
    blocking = [a for a in find_anomalies(record.draft) if a["type"] in BLOCKING]
    if blocking:
        raise Conflict(code="import_has_blocking_anomalies", anomalies=blocking[:20])
    publisher = db.get(Publisher, record.publisher_id)
    if not record.series_name:
        raise AppError(code="series_name_required")

    series = db.get(Series, record.series_id) if record.series_id else None
    duplicate = db.scalar(select(Series).where(Series.name == record.series_name))
    if duplicate and (series is None or duplicate.id != series.id):
        raise Conflict(code="series_exists", series_id=duplicate.id)  # F-39 : doublon dans le catalogue
    if series is None:
        series = Series(name=record.series_name, publisher_id=publisher.id, universe_id=record.universe_id)
        db.add(series)
    series.name, series.season, series.source = record.series_name, record.season, record.source
    series.source_date = now().date()
    series.universe_id, series.publisher_id = record.universe_id, publisher.id
    db.flush()
    record.series_id = series.id
    plan = _plan(db, record)

    # Sous-séries : retrouvées par leur nom, créées sinon.
    current_groups = {
        g.name: g for g in db.scalars(select(SeriesGroup).where(SeriesGroup.series_id == series.id))
    }
    group_rows: list[SeriesGroup] = []
    for position, group in enumerate(record.draft["groups"]):
        row = current_groups.pop(group["name"], None) or SeriesGroup(series_id=series.id, name=group["name"])
        row.kind, row.prefix, row.position = group["kind"], group["prefix"], position
        db.add(row)
        group_rows.append(row)
    db.flush()

    teams = {t.name: t for t in db.scalars(select(Team).where(Team.universe_id == series.universe_id))}

    def team_ids(names: list[str]) -> list[int]:
        ids = []
        for name in names:
            if name not in teams:
                teams[name] = Team(universe_id=series.universe_id, name=name)
                db.add(teams[name])
                db.flush()
            ids.append(teams[name].id)
        return ids

    # Deux références peuvent échanger leurs codes : on libère d'abord les codes qui changent,
    # pour ne pas heurter la contrainte d'unicité en cours de route.
    for row in plan["rows"]:
        if row["ref"] is not None and row["ref"].code_key != codes.code_key(row["code"]):
            row["ref"].code_key = f"~{row['ref'].id}"
    db.flush()

    summary = Counter()
    touched: list[tuple[CardRef, list[int]]] = []
    for row in plan["rows"]:
        ref, card = row["ref"], row["card"]
        if ref is None:
            ref = CardRef(series_id=series.id)
            db.add(ref)
            summary["added"] += 1
        ref.group_id = group_rows[row["group"]].id
        ref.code, ref.code_key = row["code"], codes.code_key(row["code"])
        ref.name, ref.rookie = card_name(card), card["rookie"]
        ref.position, ref.status = row["group"] * 100_000 + row["position"], "active"
        touched.append((ref, team_ids(card["teams"])))

    merged = CardRef.__table__.alias("merged")
    referenced = or_(
        exists().where(UserCard.card_ref_id == CardRef.id),
        exists().where(Purchase.card_ref_id == CardRef.id),
        exists().where(merged.c.merged_into_id == CardRef.id),
    )
    for ref in plan["gone"]:
        if db.scalar(select(referenced).where(CardRef.id == ref.id)):
            ref.status = "hidden"
            # Libère le code pour une éventuelle nouvelle référence.
            ref.code_key = f"~{ref.id}"
            summary["hidden"] += 1
        else:
            db.delete(ref)
            summary["deleted"] += 1
    db.flush()

    ref_ids = [ref.id for ref, _ in touched]
    db.execute(delete(CardRefTeam).where(CardRefTeam.card_ref_id.in_(ref_ids)))
    links = [{"card_ref_id": ref.id, "team_id": t} for ref, ids in touched for t in dict.fromkeys(ids)]
    if links:
        db.execute(CardRefTeam.__table__.insert(), links)
    for stale in current_groups.values():  # sous-séries disparues, si plus aucune référence ne s'y trouve
        if not db.scalar(select(exists().where(CardRef.group_id == stale.id))):
            db.delete(stale)

    series.version += 1
    series.status, series.published_at = "published", now()
    record.status = "published"
    db.add(
        SeriesVersion(series_id=series.id, version=series.version, admin_id=admin.id, summary=dict(summary))
    )
    db.flush()
    catalog.reindex_series(db, series.id)
    _link_free_purchases(db, series)
    _notify_requesters(db, series)
    return series


def _link_free_purchases(db: Session, series: Series) -> None:
    """RG-10 : les achats saisis avec ce nom de série en texte libre rejoignent le catalogue."""
    loose = db.scalars(
        select(Purchase).where(
            Purchase.series_id.is_(None), func.lower(Purchase.series_name) == series.name.lower()
        )
    ).all()
    refs = dict(db.execute(select(CardRef.code_key, CardRef.id).where(CardRef.series_id == series.id)).all())
    for purchase in loose:
        purchase.series_id, purchase.series_name = series.id, series.name
        purchase.universe_id = series.universe_id
        if purchase.code:
            purchase.card_ref_id = refs.get(codes.code_key(purchase.code))


def _notify_requesters(db: Session, series: Series) -> None:
    """F-34 : l'utilisateur est prévenu quand la série qu'il a demandée est publiée."""
    requests = db.scalars(
        select(SeriesRequest).where(SeriesRequest.series_id == series.id, SeriesRequest.status != "published")
    ).all()
    link = f"{get_settings().app_url}/catalogue/{series.id}"
    for request in requests:
        request.status = "published"
        user_ids = {
            request.user_id,
            *db.scalars(select(SeriesRequestVote.user_id).where(SeriesRequestVote.request_id == request.id)),
        }
        for user in db.scalars(
            select(User).where(User.id.in_(user_ids - {None}), User.notify_series_published)
        ):
            jobs.enqueue(
                db,
                "send_email",
                {"to": user.email, "template": "series_published", "series": series.name, "link": link},
            )


@jobs.handler("send_email")
def send_email(db: Session, job) -> None:
    payload = dict(job.payload)
    mail.send(payload.pop("to"), payload.pop("template"), **payload)
    job.payload = {"template": job.payload["template"]}  # l'adresse ne reste pas dans la file


# --------------------------------------------------------------- fusion


def merge_refs(db: Session, source: CardRef, target: CardRef) -> None:
    """F-46 : fusion de doublons. La possession, les photos et les marques suivent la cible (RG-04)."""
    if source.id == target.id or source.series_id != target.series_id:
        raise AppError(code="merge_invalid")
    for card in db.scalars(select(UserCard).where(UserCard.card_ref_id == source.id)).all():
        other = db.scalar(
            select(UserCard).where(UserCard.user_id == card.user_id, UserCard.card_ref_id == target.id)
        )
        if other is None:
            card.card_ref_id = target.id
            continue
        other.quantity = min(other.quantity + card.quantity, 999)
        other.wanted = other.wanted or card.wanted
        other.photo_id = other.photo_id or card.photo_id
        other.note = other.note or card.note
        db.execute(
            update(UserParallel).where(UserParallel.user_card_id == card.id).values(user_card_id=other.id)
        )
        db.flush()
        other.parallel_count = db.scalar(
            select(func.count()).where(UserParallel.user_card_id == other.id, UserParallel.sold.is_(False))
        )
        db.expire(card, ["parallels"])
        db.delete(card)
    db.execute(update(Purchase).where(Purchase.card_ref_id == source.id).values(card_ref_id=target.id))
    source.status, source.merged_into_id = "hidden", target.id
    source.code_key = f"~{source.id}"
    source.series.version += 1
    db.flush()
    catalog.reindex_series(db, source.series_id)
