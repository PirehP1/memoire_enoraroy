"""
crossref_full_dump.py
---------------------
Interroge l'API CrossRef pour chaque référence de la base disposant d'un DOI,
et sauvegarde la réponse JSON complète dans un fichier local.
La reprise est assurée par un ensemble d'identifiants déjà traités,
ce qui permet d'interrompre et de relancer le script sans perte de données.
"""

import mysql.connector
import requests
import json
import time
import os
from typing import Optional, Dict, List

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_CONFIG = {
    'host':     'localhost',
    'user':     'root',
    'password': 'PASSWORD',
    'database': 'DATABASE',
}

OUTPUT_FILE = 'crossref_full_dump.json'
SAVE_EVERY  = 10   # frequence de sauvegarde intermediaire (nombre de references)
SLEEP_SEC   = 1    # delai entre deux requetes (respect du rate-limit CrossRef)


# ---------------------------------------------------------------------------
# Couche reseau
# ---------------------------------------------------------------------------

MAX_RETRIES_429 = 3   # nombre maximal de tentatives en cas de rate-limit


def fetch_crossref(session: requests.Session, doi: str) -> Optional[Dict]:
    """
    Envoie une requete GET a l'API CrossRef et retourne le contenu du champ
    'message' (qui concentre toutes les metadonnees bibliographiques), ou None
    en cas d'echec.

    En cas de reponse 429 (rate-limit), une pause de 30 secondes est observee
    avant un nouvel essai, jusqu'a MAX_RETRIES_429 tentatives au total.
    """
    url = f"https://api.crossref.org/works/{doi}"

    for attempt in range(1, MAX_RETRIES_429 + 1):
        try:
            response = session.get(url, timeout=15)

            if response.status_code == 200:
                return response.json().get('message')

            if response.status_code == 404:
                print(f"    [404] DOI introuvable dans CrossRef.")
                return None

            if response.status_code == 429:
                if attempt < MAX_RETRIES_429:
                    print(f"    [429] Rate-limit atteint (tentative {attempt}/{MAX_RETRIES_429}). Pause de 30 s...")
                    time.sleep(30)
                    continue
                else:
                    print(f"    [429] Rate-limit maintenu apres {MAX_RETRIES_429} tentatives. Abandon.")
                    return None

            print(f"    [HTTP {response.status_code}] Reponse inattendue.")
            return None

        except requests.exceptions.Timeout:
            print(f"    [ERREUR] Timeout lors de la requete (tentative {attempt}/{MAX_RETRIES_429}).")
            if attempt < MAX_RETRIES_429:
                time.sleep(5)
                continue
            return None
        except Exception as exc:
            print(f"    [ERREUR] {exc}")
            return None

    return None


# ---------------------------------------------------------------------------
# Gestion de la persistance
# ---------------------------------------------------------------------------

def load_results(filename: str) -> tuple[List[Dict], set]:
    """
    Charge le fichier de resultats existant et retourne la liste des entrees
    ainsi que l'ensemble des identifiants de base de donnees deja traites.
    """
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                results = json.load(f)
            processed = {r['db_id'] for r in results}
            print(f"Reprise : {len(results)} entrees existantes, {len(processed)} IDs deja traites.")
            return results, processed
        except Exception as exc:
            print(f"Avertissement : impossible de lire {filename} ({exc}). Demarrage a zero.")

    return [], set()


def save_results(results: List[Dict], filename: str) -> None:
    """Serialise la liste des resultats en JSON avec indentation."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"  Sauvegarde : {len(results)} entrees dans '{filename}'.")


def main() -> None:
    results, processed_ids = load_results(OUTPUT_FILE)

    # Configuration du client HTTP avec un User-Agent informatif,
    # conformement aux recommandations de CrossRef.
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'BiblioFullDump/1.0 (Academic Research; mailto:contact@example.com)'
    })

    try:
        print("Connexion a la base de donnees...")
        conn   = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, doi
            FROM reference
            WHERE doi IS NOT NULL
              AND doi != ''
            ORDER BY id
        """)
        references = cursor.fetchall()
        cursor.close()
        conn.close()

        todo = [r for r in references if r['id'] not in processed_ids]
        print(f"{len(references)} references avec DOI dans la base, {len(todo)} a traiter.\n")

        if not todo:
            print("Aucune nouvelle reference a traiter.")
            return

        success, failure = 0, 0

        for i, ref in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] ID {ref['id']} — DOI : {ref['doi']}")

            data = fetch_crossref(session, ref['doi'])

            if data is not None:
                print(f"    OK — JSON enregistre ({len(json.dumps(data))} octets).")
                success += 1
            else:
                print(f"    ECHEC — aucune donnee recuperee.")
                failure += 1

            results.append({
                'db_id':   ref['id'],
                'doi':     ref['doi'],
                'found':   data is not None,
                'crossref': data          # contenu JSON complet retourne par CrossRef
            })

            if i % SAVE_EVERY == 0:
                save_results(results, OUTPUT_FILE)

            time.sleep(SLEEP_SEC)

        save_results(results, OUTPUT_FILE)

        print(f"\nTraitement termine : {success} succes, {failure} echecs sur {len(todo)} references.")
        print(f"Resultats disponibles dans '{OUTPUT_FILE}'.")

    except mysql.connector.Error as exc:
        print(f"Erreur MySQL : {exc}")
        if results:
            save_results(results, OUTPUT_FILE)

    except KeyboardInterrupt:
        print("\nInterruption utilisateur. Sauvegarde en cours...")
        save_results(results, OUTPUT_FILE)
        print("Relancez le script pour reprendre le traitement.")

    except Exception as exc:
        import traceback
        print(f"Erreur inattendue : {exc}")
        traceback.print_exc()
        if results:
            save_results(results, OUTPUT_FILE)


if __name__ == "__main__":
    main()