import requests
import json
import time
from pymongo import MongoClient
from typing import List, Dict, Set, Optional
import re
import os
from bson import ObjectId

# ============================================================
#  CONFIGURATION
# ============================================================
NAMSOR_API_KEY = "KEY"

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "references_biblio_mongo"
COLLECTION_NAME = "authors"

# Endpoint "genderize full name" (sans découpage prénom/nom)
# Doc : https://namsor.fr/documentation-api/genre/#genderize-full-name
NAMSOR_URL = "https://v2.namsor.com/NamSorAPIv2/api2/json/genderFullBatch"
NAMSOR_BATCH_SIZE = 100

OUTPUT_FILE = "auteurs_genre_impute_vsansnat.jsonl"


# ============================================================
#  GESTION DE LA PROGRESSION (reprise sans refaire le travail)
# ============================================================

def load_processed_ids() -> Set[str]:
    """Charge les IDs déjà traités depuis le fichier JSONL de résultats."""
    processed: Set[str] = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("auteur_id"):
                        processed.add(data["auteur_id"])
                except Exception:
                    continue
        print(f"DEBUG: {len(processed)} auteurs déjà présents dans {OUTPUT_FILE} — ignorés.")
    return processed


def append_result(result: dict):
    """Ajoute une ligne JSON dans le fichier de résultats (mode append)."""
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


# ============================================================
#  VALIDATION DES NOMS : a-t-on un prénom complet utilisable ?
# ============================================================

def _tokenize(text: str) -> List[str]:
    """Découpe une chaîne en tokens (séparateurs : espaces et virgules)."""
    return [t for t in re.split(r"[\s,]+", text.strip()) if t]


def _token_is_initial(token: str) -> bool:
    """
    Un token est une initiale si, après suppression du point final,
    il ne reste qu'une ou deux lettres.
    Ex : 'H', 'H.', 'KV', 'A.', 'Yu' → True
    """
    cleaned = token.rstrip(".")
    return len(cleaned) <= 2 and cleaned.isalpha()


def has_usable_full_name(name: str) -> bool:
    """
    Retourne True si le nom contient suffisamment d'information pour
    déterminer le genre (au moins une partie de prénom complète, ≥3 lettres).
    """
    if not name or not name.strip():
        return False

    name = name.strip()

    if "," in name:
        # "Nom, Prénom [Initiale.]"
        _, _, prenom_part = name.partition(",")
        prenom_tokens = _tokenize(prenom_part)
        if not prenom_tokens:
            return False
        has_full = any(not _token_is_initial(t) for t in prenom_tokens)
        return has_full

    else:
        # Pas de virgule → format "Prénom Nom" ou chaîne fusionnée
        tokens = _tokenize(name)
        if len(tokens) < 2:
            return False
        non_init = [t for t in tokens if not _token_is_initial(t)]
        if len(non_init) < 2:
            return False
        return True


# ============================================================
#  CONSTRUCTION DU NOM COMPLET À ENVOYER À NAMSOR
# ============================================================

def build_full_name(auteur: dict) -> Optional[str]:
    """
    Construit le nom complet à soumettre à NamSor.
    Priorisation corrigée pour correspondre parfaitement à la base MongoDB.
    """
    # 1. nom_complet prioritaire (format en minuscules dans MongoDB)
    if auteur.get("nom_complet"):
        val = str(auteur["nom_complet"]).strip()
        if val:
            return val

    # 2. Nom + Prenom séparés (parfois aussi présents avec cette casse)
    nom = str(auteur.get("Nom", "") or "").strip()
    prenom_raw = auteur.get("Prenom")
    if prenom_raw:
        if isinstance(prenom_raw, list):
            prenom = " ".join(str(x).strip() for x in prenom_raw if x).strip()
        else:
            prenom = str(prenom_raw).strip()
    else:
        prenom = ""

    if nom and prenom:
        return f"{nom}, {prenom}"

    # 3. Nom seul (si contient nom et prénom fusionnés)
    if nom:
        return nom

    return None


# ============================================================
#  APPEL API NAMSOR — genderFullBatch
# ============================================================

def query_namsor_full_batch(batch: List[Dict]) -> Optional[Dict]:
    """Envoie un batch à l'endpoint genderFullBatch (sans géo) de NamSor."""
    headers = {
        "X-API-KEY": NAMSOR_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {"personalNames": batch}

    try:
        response = requests.post(
            NAMSOR_URL,
            json=payload,
            headers=headers,
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()
        else:
            print(f"DEBUG: Erreur NamSor — status {response.status_code}: {response.text[:300]}")
            return None
    except Exception as e:
        print(f"DEBUG: Exception lors de l'appel NamSor: {e}")
        return None


# ============================================================
#  MAIN
# ============================================================

def main():
    print("=" * 60)
    print("Détection globale de genre (Sans filtres géographiques)")
    print("=" * 60)

    # --- Connexion MongoDB ---
    print(f"DEBUG: Connexion à MongoDB ({MONGO_URI}) — base: {DB_NAME}")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    # --- IDs déjà traités (reprise) ---
    already_done = load_processed_ids()

    # --- Requête MongoDB Robuste ---
    # Cible tous les auteurs qui n'ont aucun genre assigné
    mongo_query: dict = {
        "$or": [
            {"genre": {"$exists": False}},
            {"genre.valeur": {"$exists": False}},
            {"genre.valeur": {"$in": [None, '', ' ']}}
        ]
    }
    
    if already_done:
        excluded_oids = []
        for sid in already_done:
            try:
                excluded_oids.append(ObjectId(sid))
            except Exception:
                pass
        if excluded_oids:
            mongo_query["_id"] = {"$nin": excluded_oids}

    print("DEBUG: Exécution de la requête sur MongoDB...")
    auteurs = list(collection.find(mongo_query))
    print(f"DEBUG: {len(auteurs)} auteurs récupérés depuis MongoDB à analyser.")

    # --- Préparation du batch NamSor ---
    namsor_batch: List[Dict] = []
    auteur_meta: Dict[str, dict] = {}  # auteur_id → doc mongo
    skipped = 0

    for auteur in auteurs:
        auteur_id = str(auteur["_id"])
        auteur_meta[auteur_id] = auteur

        full_name = build_full_name(auteur)

        if not full_name:
            skipped += 1
            append_result({
                "auteur_id": auteur_id,
                "cle": auteur.get("cle", ""),
                "nom_utilise": None,
                "traitable": False,
                "raison_rejet": "Aucun champ nom disponible",
                "genre_identifie": None,
                "probabilite": None,
                "namsor_result": None,
            })
            continue

        if not has_usable_full_name(full_name):
            # Nom trop court ou composé d'initiales uniquement
            skipped += 1
            append_result({
                "auteur_id": auteur_id,
                "cle": auteur.get("cle", ""),
                "nom_utilise": full_name,
                "traitable": False,
                "raison_rejet": "Prénom incomplet ou initiale uniquement",
                "genre_identifie": None,
                "probabilite": None,
                "namsor_result": None,
            })
            continue

        # Nom valide → ajout au batch
        namsor_batch.append({"id": auteur_id, "name": full_name})

    print(f"\nDEBUG: {len(namsor_batch)} noms valides vont être envoyés à NamSor.")
    print(f"DEBUG: {skipped} auteurs ignorés d'office (noms invalides) — logs sauvegardés.")

    if not namsor_batch:
        print("\nFin du traitement : Aucun nouvel auteur éligible trouvé.")
        return

    # --- Traitement par batch ---
    total_batches = max(1, (len(namsor_batch) + NAMSOR_BATCH_SIZE - 1) // NAMSOR_BATCH_SIZE)

    for batch_start in range(0, len(namsor_batch), NAMSOR_BATCH_SIZE):
        batch = namsor_batch[batch_start: batch_start + NAMSOR_BATCH_SIZE]
        batch_num = batch_start // NAMSOR_BATCH_SIZE + 1
        print(f"DEBUG: Batch {batch_num}/{total_batches} — {len(batch)} noms envoyés...")

        name_by_id = {item["id"]: item["name"] for item in batch}
        response = query_namsor_full_batch(batch)

        if response and "personalNames" in response:
            for result in response["personalNames"]:
                auteur_id = result.get("id")
                if not auteur_id:
                    continue

                auteur = auteur_meta.get(auteur_id, {})
                genre = result.get("likelyGender")
                proba = result.get("probabilityCalibrated")

                record = {
                    "auteur_id": auteur_id,
                    "cle": auteur.get("cle", ""),
                    "nom_utilise": name_by_id.get(auteur_id),
                    "traitable": True,
                    "raison_rejet": None,
                    "genre_identifie": genre,
                    "probabilite": proba,
                    "namsor_result": result,
                }
                append_result(record)
        else:
            print(f"DEBUG: Échec du batch {batch_num} — Enregistrement des erreurs.")
            for item in batch:
                auteur_id = item["id"]
                auteur = auteur_meta.get(auteur_id, {})
                append_result({
                    "auteur_id": auteur_id,
                    "cle": auteur.get("cle", ""),
                    "nom_utilise": item["name"],
                    "traitable": True,
                    "raison_rejet": "Erreur API NamSor (batch échoué)",
                    "genre_identifie": None,
                    "probabilite": None,
                    "namsor_result": None,
                })

        # Pause rate-limit réglementaire entre les batches
        if batch_start + NAMSOR_BATCH_SIZE < len(namsor_batch):
            time.sleep(0.4)

    # --- Résumé final ---
    total_in_file = len(load_processed_ids())
    print(f"\n{'='*60}")
    print(f"Traitement terminé avec succès.")
    print(f"  Fichier mis à jour : {OUTPUT_FILE}")
    print(f"  Total cumulé dans le fichier : {total_in_file} auteurs")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()