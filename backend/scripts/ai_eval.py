"""Jeu d'essai de la lecture de photo (IA-05).

Mesure la qualité à chaque changement de modèle ou de consigne :

    CC_AI_BACKEND=anthropic CC_ANTHROPIC_API_KEY=… \
        uv run python -m scripts.ai_eval DOSSIER [--model claude-sonnet-5-5]

DOSSIER contient, par cas, une photo et un fichier JSON du même nom :
    griezmann-gold.jpg
    griezmann-gold.json   {"serie": "Topps Chrome Sapphire UEFA Club Competitions 2024/25",
                           "numero": "8", "nom": "Antoine Griezmann", "variante": "Gold 35/50"}
et, facultatif, `series.txt` : les noms de séries proposés au modèle, un par ligne.

Les 48 photos d'achats du prototype, avec leurs fiches vérifiées, forment le premier jeu d'essai.
"""

import argparse
import io
import json
from pathlib import Path

from PIL import Image, ImageOps

from app.rules.search import fold
from app.services import ai

FIELDS = ("serie", "numero", "nom", "variante")


def prepare(path: Path) -> bytes:
    """Même préparation que l'application : orientation appliquée, 800 px, WebP."""
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    image.thumbnail((800, 800))
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=82)
    return buffer.getvalue()


def same(expected: str, got: str) -> bool:
    return fold(expected).replace(" ", "") == fold(got).replace(" ", "")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--model")
    args = parser.parse_args()
    provider = ai.get_provider()
    if provider is None:
        raise SystemExit("IA désactivée : réglez CC_AI_BACKEND.")
    if args.model:
        provider.photo_model = args.model
    series_file = args.folder / "series.txt"
    series = series_file.read_text(encoding="utf-8").splitlines() if series_file.exists() else []

    hits = dict.fromkeys(FIELDS, 0)
    cases, tokens_in, tokens_out = 0, 0, 0
    for expected_file in sorted(args.folder.glob("*.json")):
        photo = next(
            (p for p in expected_file.parent.glob(f"{expected_file.stem}.*") if p.suffix != ".json"), None
        )
        if photo is None:
            continue
        expected = json.loads(expected_file.read_text(encoding="utf-8"))
        reading, usage = provider.read_card(prepare(photo), series)
        cases += 1
        tokens_in, tokens_out = tokens_in + usage.input_tokens, tokens_out + usage.output_tokens
        misses = [f for f in FIELDS if not same(expected.get(f, ""), getattr(reading, f))]
        for field in FIELDS:
            hits[field] += field not in misses
        if misses:
            details = "; ".join(
                f"{f} : attendu « {expected.get(f, '')} », lu « {getattr(reading, f)} »" for f in misses
            )
            print(f"{photo.name} — {details}")
    if not cases:
        raise SystemExit("Aucun cas dans ce dossier.")
    cost = ai.estimate_cost(provider.photo_model, ai.Usage(tokens_in, tokens_out))
    print(f"\n{cases} cas, modèle {provider.photo_model}")
    for field in FIELDS:
        print(f"  {field:9} {hits[field] * 100 // cases:3d} %")
    print(f"  coût moyen par lecture : {cost / cases:.5f} $")


if __name__ == "__main__":
    main()
