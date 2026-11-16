"""Photos des utilisateurs (RG-14, T-04)."""

import hashlib
import io
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError, NotFound
from app.models import PersonalCard, Photo, Purchase, User, UserCard, UserParallel
from app.storage import get_storage

register_heif_opener()  # les iPhone envoient parfois du HEIC

SIZES = {"thumb": 320, "medium": 800, "large": 1600}  # T-04 : vignette, moyenne, 1 600 px
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF", "MPO"}
Image.MAX_IMAGE_PIXELS = 60_000_000  # refuse les images piégées (bombes de décompression)


def _key(photo: Photo, size: str) -> str:
    return f"{photo.key_prefix}/{size}.webp"


def store(db: Session, user: User, raw: bytes) -> Photo:
    """Enregistre une photo en trois tailles.

    L'image est décodée puis ré-encodée : le type est vérifié sur le contenu (S-04) et aucune
    métadonnée — position GPS, appareil — ne survit (RG-14, CA-04).
    """
    if len(raw) > get_settings().photo_max_bytes:
        raise AppError(code="photo_too_large", max_bytes=get_settings().photo_max_bytes)

    digest = hashlib.sha256(raw).hexdigest()
    existing = db.scalar(select(Photo).where(Photo.user_id == user.id, Photo.sha256 == digest))
    if existing:
        return existing  # la même photo sert à l'achat et à la carte

    try:
        image = Image.open(io.BytesIO(raw))
        if image.format not in ALLOWED_FORMATS:
            raise AppError(code="photo_unsupported")
        image = ImageOps.exif_transpose(image).convert("RGB")  # applique l'orientation, puis l'oublie
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise AppError(code="photo_unsupported") from error

    photo = Photo(id=uuid.uuid4(), user_id=user.id, sha256=digest, width=0, height=0, bytes=0, key_prefix="")
    photo.key_prefix = f"photos/{user.id}/{photo.id}"
    storage = get_storage()
    total = 0
    for size, edge in SIZES.items():
        resized = image.copy()
        resized.thumbnail((edge, edge), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        resized.save(buffer, "WEBP", quality=82, method=4)  # aucun paramètre exif : rien n'est recopié
        storage.put(_key(photo, size), buffer.getvalue(), "image/webp")
        total += buffer.tell()
        if size == "large":
            photo.width, photo.height = resized.size
    photo.bytes = total
    db.add(photo)
    db.flush()
    return photo


def owned(db: Session, user: User, photo_id: uuid.UUID | None) -> Photo | None:
    """La photo, si elle appartient à l'utilisateur. Sert à valider tout `photo_id` reçu."""
    if photo_id is None:
        return None
    photo = db.get(Photo, photo_id)
    if photo is None or photo.user_id != user.id:
        raise NotFound(code="photo_not_found")
    return photo


def is_used(db: Session, photo_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(
                or_(
                    exists().where(UserCard.photo_id == photo_id),
                    exists().where(UserParallel.photo_id == photo_id),
                    exists().where(Purchase.photo_id == photo_id),
                    exists().where(PersonalCard.photo_id == photo_id),
                    exists().where(User.avatar_photo_id == photo_id),
                )
            )
        )
    )


def release(db: Session, photo_id: uuid.UUID | None) -> None:
    """RG-14 : une photo n'est supprimée du stockage que lorsque plus rien ne l'utilise."""
    if photo_id is None:
        return
    db.flush()
    if is_used(db, photo_id):
        return
    photo = db.get(Photo, photo_id)
    if photo:
        get_storage().delete([_key(photo, size) for size in SIZES])
        db.delete(photo)


def read(photo: Photo, size: str) -> tuple[bytes | None, str | None]:
    """(contenu, adresse signée) : l'un des deux selon le stockage."""
    if size not in SIZES:
        raise NotFound()
    storage = get_storage()
    url = storage.signed_url(_key(photo, size))
    return (None, url) if url else (storage.get(_key(photo, size)), None)


def delete_all_for_user(db: Session, user_id: uuid.UUID) -> int:
    """Efface du stockage toutes les photos d'un compte (F-31)."""
    photos = db.scalars(select(Photo).where(Photo.user_id == user_id)).all()
    get_storage().delete([_key(p, size) for p in photos for size in SIZES])
    return len(photos)
