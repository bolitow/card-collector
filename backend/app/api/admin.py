"""Administration (section 6.6). Toute route exige le rôle administrateur et la double authentification."""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, UploadFile
from sqlalchemy import delete, func, or_, select

from app import security
from app.api.catalog import open_queue_count, series_out
from app.deps import AdminUser, Db, admin_user
from app.errors import AppError, Conflict, NotFound
from app.models import (
    AiCall,
    AuditLog,
    CardRef,
    ChaseMark,
    ChecklistImport,
    Job,
    OfficialParallel,
    Photo,
    Publisher,
    Report,
    Series,
    SeriesRequest,
    SeriesRequestVote,
    SeriesVersion,
    Universe,
    User,
    UserSeries,
    UserSession,
)
from app.schemas import (
    AdminSeriesIn,
    AdminSeriesOut,
    AdminUserIn,
    AdminUserOut,
    AnomalyOut,
    AuditOut,
    ChaseIn,
    Draft,
    ImportDetailOut,
    ImportIn,
    ImportOut,
    ImportPatch,
    JobOut,
    MergeIn,
    NamedIn,
    PublisherOut,
    QueueItemOut,
    QueueReplyIn,
    StatsOut,
    UniverseIn,
    UniverseOut,
)
from app.services import accounts, imports, jobs
from app.services import photos as photo_service
from app.storage import get_storage

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(admin_user)])


def audit(db, admin: User, action: str, target: str = "", reason: str = "", **data) -> None:
    """RG-01, F-49 : chaque action d'un administrateur est tracée."""
    db.add(AuditLog(admin_id=admin.id, action=action, target=target, reason=reason, data=data))


# ----------------------------------------------------------------- imports


def _import(db, import_id: int) -> ChecklistImport:
    record = db.get(ChecklistImport, import_id)
    if record is None:
        raise NotFound(code="import_not_found")
    return record


def _import_out(record: ChecklistImport) -> dict:
    draft = record.draft or {"groups": []}
    return {
        "id": record.id,
        "status": record.status,
        "series_id": record.series_id,
        "series_name": record.series_name,
        "season": record.season,
        "source": record.source,
        "universe_id": record.universe_id,
        "publisher_id": record.publisher_id,
        "error": record.error,
        "created_at": record.created_at,
        "counters": imports.counters(draft) if draft.get("groups") is not None else {},
    }


def _import_detail(db, record: ChecklistImport) -> ImportDetailOut:
    draft = imports.normalize_draft(record.draft or {})
    anomalies = [
        AnomalyOut(**a, blocking=a["type"] in imports.BLOCKING) for a in imports.find_anomalies(draft)
    ]
    publisher = db.get(Publisher, record.publisher_id)
    return ImportDetailOut(
        **_import_out(record),
        draft=Draft(**draft),
        anomalies=anomalies,
        name_problems=imports.check_series_name(db, record, publisher) if record.status == "review" else [],
    )


@router.get("/imports")
def list_imports(db: Db) -> list[ImportOut]:
    rows = db.scalars(select(ChecklistImport).order_by(ChecklistImport.created_at.desc()).limit(50))
    return [ImportOut(**_import_out(r)) for r in rows]


@router.post("/imports", status_code=201)
def create_import(body: ImportIn, admin: AdminUser, db: Db) -> ImportOut:
    """F-36, étape 1 : texte collé."""
    record = imports.create(db, admin, body.model_dump())
    audit(db, admin, "import.create", f"import:{record.id}", series=record.series_name)
    return ImportOut(**_import_out(record))


@router.post("/imports/pdf", status_code=201)
async def create_import_pdf(
    file: UploadFile,
    admin: AdminUser,
    db: Db,
    universe_id: int = Form(),
    publisher_id: int = Form(),
    series_name: str = Form(""),
    season: str = Form(""),
    source: str = Form(""),
    use_ai: bool = Form(True),
) -> ImportOut:
    """F-36, étape 1 : dépôt du PDF de l'éditeur. Le PDF n'est pas conservé (10.3) : seul son texte l'est."""
    pdf = await file.read(30 * 1024 * 1024 + 1)
    if len(pdf) > 30 * 1024 * 1024 or not pdf.startswith(b"%PDF"):
        raise AppError(code="pdf_invalid")
    data = {
        "universe_id": universe_id,
        "publisher_id": publisher_id,
        "series_name": series_name,
        "season": season,
        "source": source or (file.filename or ""),
        "use_ai": use_ai,
    }
    record = imports.create(db, admin, data, pdf)
    audit(db, admin, "import.create", f"import:{record.id}", series=record.series_name)
    return ImportOut(**_import_out(record))


@router.get("/imports/{import_id}")
def get_import(import_id: int, db: Db) -> ImportDetailOut:
    return _import_detail(db, _import(db, import_id))


@router.patch("/imports/{import_id}")
def update_import(import_id: int, body: ImportPatch, db: Db) -> ImportDetailOut:
    """Étape 3 : relecture. Le brouillon corrigé remplace l'ancien ; les anomalies sont recalculées."""
    record = _import(db, import_id)
    if record.status != "review":
        raise Conflict(code="import_not_ready")
    data = body.model_dump(exclude_unset=True)
    if "draft" in data:
        record.draft = imports.normalize_draft(data.pop("draft"))
    for field, value in data.items():
        if value is not None:
            setattr(record, field, value.strip() if isinstance(value, str) else value)
    db.flush()
    return _import_detail(db, record)


@router.get("/imports/{import_id}/diff")
def import_diff(import_id: int, db: Db) -> dict:
    """F-38 : changements par rapport à la version publiée, avant publication."""
    record = _import(db, import_id)
    if record.status != "review":
        raise Conflict(code="import_not_ready")
    return imports.diff(db, record)


@router.post("/imports/{import_id}/publish")
def publish_import(import_id: int, admin: AdminUser, db: Db) -> dict:
    record = _import(db, import_id)
    series = imports.publish(db, admin, record)
    audit(db, admin, "series.publish", f"series:{series.id}", version=series.version, name=series.name)
    return {"series_id": series.id, "version": series.version}


@router.delete("/imports/{import_id}", status_code=204)
def delete_import(import_id: int, db: Db) -> None:
    db.delete(_import(db, import_id))


@router.get("/jobs/{job_id}")
def job(job_id: UUID, db: Db) -> JobOut:
    row = db.get(Job, job_id)
    if row is None:
        raise NotFound()
    return JobOut.model_validate(row)


# --------------------------------------------------------------- catalogue


@router.get("/series")
def list_series(db: Db, q: str = "") -> list[AdminSeriesOut]:
    followers = dict(
        db.execute(
            select(UserSeries.series_id, func.count())
            .where(UserSeries.status == "followed", UserSeries.series_id.is_not(None))
            .group_by(UserSeries.series_id)
        ).all()
    )
    statement = select(Series).order_by(Series.updated_at.desc())
    if q:
        statement = statement.where(Series.name.ilike(f"%{q}%"))
    return [
        AdminSeriesOut(**series_out(s), status=s.status, followers=followers.get(s.id, 0))
        for s in db.scalars(statement.limit(300))
    ]


@router.patch("/series/{series_id}")
def update_series(series_id: int, body: AdminSeriesIn, admin: AdminUser, db: Db) -> AdminSeriesOut:
    series = db.get(Series, series_id)
    if series is None:
        raise NotFound(code="series_not_found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"]:
        series.status = data["status"]  # masquer une série ne supprime rien (RG-04)
    if "release_date" in data:
        series.release_date = data["release_date"]
    audit(db, admin, "series.update", f"series:{series.id}", **{k: str(v) for k, v in data.items()})
    followers = db.scalar(
        select(func.count()).where(UserSeries.series_id == series.id, UserSeries.status == "followed")
    )
    return AdminSeriesOut(**series_out(series), status=series.status, followers=followers or 0)


@router.post("/series/{series_id}/edit", status_code=201)
def edit_series(series_id: int, admin: AdminUser, db: Db) -> ImportOut:
    """F-38 : ouvre la série publiée en brouillon pour la corriger ou la compléter."""
    series = db.get(Series, series_id)
    if series is None:
        raise NotFound(code="series_not_found")
    return ImportOut(**_import_out(imports.from_series(db, admin, series)))


@router.get("/series/{series_id}/versions")
def series_versions(series_id: int, db: Db) -> list[dict]:
    rows = db.scalars(
        select(SeriesVersion)
        .where(SeriesVersion.series_id == series_id)
        .order_by(SeriesVersion.version.desc())
    )
    return [{"version": r.version, "published_at": r.published_at, "summary": r.summary} for r in rows]


@router.post("/refs/merge", status_code=204)
def merge_refs(body: MergeIn, admin: AdminUser, db: Db) -> None:
    """F-46 : fusion de deux références en doublon."""
    source, target = db.get(CardRef, body.source_id), db.get(CardRef, body.target_id)
    if source is None or target is None:
        raise NotFound(code="card_not_found")
    imports.merge_refs(db, source, target)
    audit(db, admin, "ref.merge", f"ref:{source.id}", into=target.id)


@router.put("/refs/{ref_id}/chase", status_code=204)
def set_chase(ref_id: int, body: ChaseIn, admin: AdminUser, db: Db) -> None:
    """RG-17 : marque éditoriale, avec une raison et une date."""
    ref = db.get(CardRef, ref_id)
    if ref is None:
        raise NotFound(code="card_not_found")
    mark = db.get(ChaseMark, ref_id) or ChaseMark(card_ref_id=ref_id)
    mark.reason, mark.sources, mark.author_id = body.reason, body.sources, admin.id
    mark.marked_on = security.now().date()
    db.add(mark)
    ref.series.version += 1  # la checklist en cache porte les marques
    audit(db, admin, "chase.set", f"ref:{ref_id}", reason=body.reason)


@router.delete("/refs/{ref_id}/chase", status_code=204)
def unset_chase(ref_id: int, admin: AdminUser, db: Db) -> None:
    mark = db.get(ChaseMark, ref_id)
    if mark:
        ref = db.get(CardRef, ref_id)
        ref.series.version += 1
        db.delete(mark)
        audit(db, admin, "chase.unset", f"ref:{ref_id}")


@router.put("/series/{series_id}/parallels", status_code=204)
def set_official_parallels(series_id: int, names: list[str], admin: AdminUser, db: Db) -> None:
    """Parallèles officiels de la série, proposés en suggestion (F-16)."""
    if db.get(Series, series_id) is None:
        raise NotFound(code="series_not_found")
    db.execute(delete(OfficialParallel).where(OfficialParallel.series_id == series_id))
    db.add_all(
        OfficialParallel(series_id=series_id, name=n.strip()[:80]) for n in dict.fromkeys(names) if n.strip()
    )
    audit(db, admin, "parallels.set", f"series:{series_id}", count=len(names))


@router.post("/universes", status_code=201)
def create_universe(body: UniverseIn, admin: AdminUser, db: Db) -> UniverseOut:
    """ENF-05 : un univers s'ajoute sans modifier le code."""
    universe = Universe(**body.model_dump())
    db.add(universe)
    db.flush()
    audit(db, admin, "universe.create", f"universe:{universe.id}", name=universe.name)
    return UniverseOut.model_validate(universe)


@router.patch("/universes/{universe_id}")
def update_universe(universe_id: int, body: UniverseIn, admin: AdminUser, db: Db) -> UniverseOut:
    universe = db.get(Universe, universe_id)
    if universe is None:
        raise NotFound()
    for field, value in body.model_dump().items():
        setattr(universe, field, value)
    audit(db, admin, "universe.update", f"universe:{universe.id}")
    return UniverseOut.model_validate(universe)


@router.get("/publishers")
def list_publishers(db: Db) -> list[PublisherOut]:
    return [PublisherOut.model_validate(p) for p in db.scalars(select(Publisher).order_by(Publisher.name))]


@router.post("/publishers", status_code=201)
def create_publisher(body: NamedIn, admin: AdminUser, db: Db) -> PublisherOut:
    if db.scalar(select(Publisher).where(Publisher.name == body.name.strip())):
        raise Conflict(code="publisher_exists")
    publisher = Publisher(name=body.name.strip())
    db.add(publisher)
    db.flush()
    audit(db, admin, "publisher.create", f"publisher:{publisher.id}", name=publisher.name)
    return PublisherOut.model_validate(publisher)


# ---------------------------------------------------------- file de travail


@router.get("/queue")
def queue(db: Db, status: str = "open") -> list[QueueItemOut]:
    """F-48 : demandes de séries et signalements, les plus demandés d'abord."""
    items: list[QueueItemOut] = []
    votes = dict(
        db.execute(
            select(SeriesRequestVote.request_id, func.count()).group_by(SeriesRequestVote.request_id)
        ).all()
    )
    authors = {u.id: u.pseudo for u in db.scalars(select(User))} if status else {}
    for r in db.scalars(select(SeriesRequest).where(SeriesRequest.status == status)):
        items.append(
            QueueItemOut(
                kind="request",
                id=r.id,
                status=r.status,
                title=r.name,
                detail="\n".join(x for x in (r.url, r.note) if x),
                author=authors.get(r.user_id),
                votes=votes.get(r.id, 0) + 1,
                admin_reply=r.admin_reply,
                created_at=r.created_at,
                series_id=r.series_id,
            )
        )
    for r in db.scalars(select(Report).where(Report.status == status)):
        ref = db.get(CardRef, r.card_ref_id) if r.card_ref_id else None
        title = "Contenu signalé" if r.kind == "content" else "Erreur du catalogue"
        if ref:
            title = f"{title} — {ref.series.name} n° {ref.code}"
        items.append(
            QueueItemOut(
                kind="report",
                id=r.id,
                status=r.status,
                title=title,
                detail=r.message,
                author=authors.get(r.reporter_id),
                admin_reply=r.admin_reply,
                created_at=r.created_at,
                series_id=r.series_id or (ref.series_id if ref else None),
                card_ref_id=r.card_ref_id,
                target_pseudo=authors.get(r.target_user_id),
                photo_id=r.photo_id,
            )
        )
    items.sort(key=lambda item: (-item.votes, item.created_at))
    return items


@router.patch("/queue/{kind}/{item_id}", status_code=204)
def answer(kind: str, item_id: int, body: QueueReplyIn, admin: AdminUser, db: Db) -> None:
    """Chaque élément a un statut et une réponse à l'utilisateur (F-48)."""
    model = SeriesRequest if kind == "request" else Report
    allowed = (
        ("open", "accepted", "declined", "published")
        if kind == "request"
        else ("open", "resolved", "dismissed")
    )
    item = db.get(model, item_id)
    if item is None or body.status not in allowed:
        raise NotFound()
    item.status, item.admin_reply = body.status, body.admin_reply.strip()
    if kind == "request" and body.series_id:
        item.series_id = body.series_id
    author_id = item.user_id if kind == "request" else item.reporter_id
    author = db.get(User, author_id) if author_id else None
    if author and item.admin_reply and body.status != "open":
        subject = item.name if kind == "request" else "Votre signalement"
        jobs.enqueue(
            db,
            "send_email",
            {
                "to": author.email,
                "template": "request_answered",
                "subject": subject,
                "reply": item.admin_reply,
            },
        )
    audit(db, admin, f"{kind}.answer", f"{kind}:{item_id}", status=body.status)


@router.delete("/photos/{photo_id}", status_code=204)
def remove_photo(photo_id: UUID, admin: AdminUser, db: Db, reason: str = Query(min_length=3)) -> None:
    """Modération (10.3) : retrait rapide d'une photo signalée."""
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise NotFound()
    get_storage().delete([f"{photo.key_prefix}/{size}.webp" for size in photo_service.SIZES])
    db.delete(photo)  # les cartes et achats qui l'utilisaient perdent leur photo (ON DELETE SET NULL)
    audit(db, admin, "photo.remove", f"photo:{photo_id}", reason, owner=str(photo.user_id))


# ------------------------------------------------------------- utilisateurs


def _user_out(db, user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email,
        pseudo=user.pseudo,
        role=user.role,
        status=user.status,
        plan=user.plan,
        created_at=user.created_at,
        last_seen_at=user.last_seen_at,
        ai_quota_day=user.ai_quota_day,
        ai_quota_month=user.ai_quota_month,
        collections=db.scalar(select(func.count()).where(UserSeries.user_id == user.id)) or 0,
        photos=db.scalar(select(func.count()).where(Photo.user_id == user.id)) or 0,
    )


@router.get("/users")
def users(db: Db, q: str = Query("", max_length=100)) -> list[AdminUserOut]:
    """F-49 : recherche par e-mail ou pseudonyme. Ne donne accès à aucune donnée de collection."""
    statement = select(User).order_by(User.created_at.desc()).limit(50)
    if q:
        statement = statement.where(or_(User.email.ilike(f"%{q}%"), User.pseudo.ilike(f"%{q}%")))
    return [_user_out(db, u) for u in db.scalars(statement)]


@router.patch("/users/{user_id}")
def update_user(user_id: UUID, body: AdminUserIn, admin: AdminUser, db: Db) -> AdminUserOut | None:
    """Suspension, suppression à la demande, quotas d'IA. Un motif est obligatoire (RG-01)."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFound()
    if body.delete:
        if user.id == admin.id:
            raise Conflict(code="cannot_delete_self")
        audit(db, admin, "user.delete", f"user:{user.id}", body.reason)
        accounts.request_deletion(db, user, accounts.DELETE_WORD)
        return None
    if body.status:
        user.status, user.suspended_reason = body.status, body.reason if body.status == "suspended" else None
        if body.status == "suspended":
            db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    if body.reset_quotas:
        user.ai_quota_day = user.ai_quota_month = None
    if body.ai_quota_day is not None:
        user.ai_quota_day = body.ai_quota_day
    if body.ai_quota_month is not None:
        user.ai_quota_month = body.ai_quota_month
    audit(
        db,
        admin,
        "user.update",
        f"user:{user.id}",
        body.reason,
        **body.model_dump(exclude={"reason"}, exclude_none=True),
    )
    db.flush()
    return _user_out(db, user)


@router.get("/audit")
def audit_log(db: Db, limit: int = 100) -> list[AuditOut]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500)))
    return [AuditOut.model_validate(r) for r in rows]


@router.get("/stats")
def stats(db: Db) -> StatsOut:
    """F-50 : tableau de bord."""
    month = security.now() - timedelta(days=30)
    top = db.execute(
        select(Series.name, func.count())
        .join(UserSeries, UserSeries.series_id == Series.id)
        .where(UserSeries.status == "followed")
        .group_by(Series.name)
        .order_by(func.count().desc())
        .limit(10)
    ).all()
    calls, cost = db.execute(
        select(func.count(), func.coalesce(func.sum(AiCall.cost_usd), 0)).where(AiCall.created_at >= month)
    ).one()
    photo_count, photo_bytes = db.execute(select(func.count(), func.coalesce(func.sum(Photo.bytes), 0))).one()
    return StatsOut(
        users=db.scalar(select(func.count()).select_from(User)) or 0,
        users_30d=db.scalar(select(func.count()).where(User.created_at >= month)) or 0,
        active_30d=db.scalar(select(func.count()).where(User.last_seen_at >= month)) or 0,
        photos=photo_count,
        photo_bytes=photo_bytes,
        ai_calls_30d=calls,
        ai_cost_30d=cost,
        top_series=[{"name": name, "followers": count} for name, count in top],
        queue_open=open_queue_count(db),
    )
