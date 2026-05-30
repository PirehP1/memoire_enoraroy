import numpy as np
import pandas as pd
import networkx as nx
from pathlib import Path
from scipy.stats import spearmanr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE         = Path(__file__).resolve().parent.parent
EDGES_PATH   = BASE / "Noeuds_et_aretes" / "edges_author_pub.csv"
NODES_PATH   = BASE / "Noeuds_et_aretes" / "nodes_all.csv"
METRICS_PATH = BASE / "output" / "auteur_simple_nodes.csv"
OUTPUT_DIR   = BASE / "output" / "spearman_simple"
METRICS      = ["degree", "closeness", "betweenness", "eigenvector"] # Centralités étudiées
TOP_PERCENT  = 1      # Seuil pour le Run B (on garde le top 1% des auteurs les plus centraux)
MIN_LCC_SIZE = 200    # Taille minimale pour qu'une LCC soit considérée comme "stable" -> annéee 2000, car avant la LCC n'est pas stable!
MIN_YEAR     = 2000   # Année de départ pour l'analyse temporelle


df_e = pd.read_csv(EDGES_PATH, dtype=str, low_memory=False)
df_e.columns = df_e.columns.str.strip().str.lower()
df_e["source"] = df_e["source"].astype(str).str.strip()
df_e["target"] = df_e["target"].astype(str).str.strip()
df_e["year"]   = pd.to_numeric(df_e["year"], errors="coerce")
df_e           = df_e.dropna(subset=["year"])
df_e["year"]   = df_e["year"].astype(int)

df_n = pd.read_csv(NODES_PATH, dtype=str, low_memory=False)
df_n.columns = df_n.columns.str.strip().str.lower()
df_n["id"]   = df_n["id"].astype(str).str.strip()

df_m = pd.read_csv(METRICS_PATH, dtype=str, low_memory=False)
df_m.columns = df_m.columns.str.strip().str.lower()
df_m["id"]   = df_m["id"].astype(str).str.strip()
for m in METRICS:
    if m in df_m.columns:
        df_m[m] = pd.to_numeric(df_m[m], errors="coerce")

print(f"Arêtes : {len(df_e):,} | Auteurs dans metrics : {len(df_m):,}")

years             = sorted(df_e["year"].unique()) # Liste triée des années chronologiques
entry             = {} # Dictionnaire pour stocker {id_auteur: annee_entree_lcc}
G                 = nx.Graph() # Initialisation d'un réseau NetworkX vide
prev_lcc          = set()      # Stocke la LCC de l'année précédente
first_stable_seen = False      # Drapeau pour identifier le point de départ de la LCC stable

# évolution du réseau année par année (approche cumulative)
for yr in years:
    edges_yr = df_e[df_e["year"] == yr]
    # On ajoute les nouvelles arêtes de l'année courante au graphe global
    G.add_edges_from(zip(edges_yr["source"], edges_yr["target"]))

    if G.number_of_nodes() == 0:
        continue

    # Extraction de la plus grande composante connexe (LCC) à l'instant t
    lcc    = max(nx.connected_components(G), key=len)
    lcc_sz = len(lcc)

    # Filtre de sécurité : on ignore les années trop anciennes ou les composantes trop petites
    if yr < MIN_YEAR or lcc_sz < MIN_LCC_SIZE:
        print(f"  {yr} | LCC={lcc_sz:>5} | hors zone")
        continue

    # Si c'est la première année où la LCC dépasse le seuil minimal (200)
    if not first_stable_seen:
        first_stable_seen = True
        for node in lcc:
            entry[node] = yr # Tous les membres actuels de cette LCC ont cette année comme année d'entrée
        print(f"  {yr} | LCC={lcc_sz:>5} | *** PREMIÈRE LCC STABLE — {lcc_sz} auteurs ***")
    else:
        # Pour les années suivantes, on regarde qui vient d'entrer dans la LCC (différence d'ensembles)
        new_in = lcc - prev_lcc
        for node in new_in:
            if node not in entry: # Sécurité pour éviter d'écraser une année déjà enregistrée
                entry[node] = yr
        print(f"  {yr} | LCC={lcc_sz:>5} | nouveaux entrants = {len(new_in)}")

    prev_lcc = lcc # Mise à jour de la LCC de référence pour l'année suivante

# Filtrage pour ne garder que les identifiants qui correspondent bien à des "auteurs"
if "type" in df_n.columns:
    author_ids = set(df_n.loc[df_n["type"].str.lower().str.strip() == "author", "id"])
else:
    author_ids = set(df_e["source"].unique())

# Création du DataFrame final contenant l'historique des entrées
df_entry = pd.DataFrame(
    [(node, yr) for node, yr in entry.items() if node in author_ids],
    columns=["id", "year_entry"]
)
print(f"\nAuteurs avec une année d'entrée : {len(df_entry):,}")

print("\n=== Construction du dataset ===")

df = df_entry.merge(df_m[["id"] + METRICS], on="id", how="inner")
print(f"Dataset complet : {len(df):,} auteurs | "
      f"années : {int(df['year_entry'].min())}–{int(df['year_entry'].max())}")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
df.to_csv(OUTPUT_DIR / "dataset.csv", index=False)


def run_spearman(sub, m):
    """Calcule le coefficient rho de Spearman et détermine le sens de la corrélation."""
    # spearmanr renvoie (rho, p_value). On ignore la p_value en la stockant dans '_'
    rho, _ = spearmanr(sub["year_entry"], sub[m])
    
    # Interprétation empirique du signe de rho
    direction = "anciens → centralité plus haute" if rho < 0 else "récents → centralité plus haute"
    return rho, direction

print(f"\n=== RUN A : Population complète (n = {len(df):,}) ===\n")

results_a = []
for m in METRICS:
    sub = df[["year_entry", m]].dropna() # Nettoyage des valeurs manquantes pour la métrique courante
    rho, direction = run_spearman(sub, m)
    print(f"  {m:<15} {rho:>8.4f}")
    results_a.append({
        "run": "complet", "indicateur": m, "n": len(sub),
        "rho": round(rho, 4), "direction": direction
    })


threshold = 1 - TOP_PERCENT / 100 # Calcul du quantile (ex: top 1% -> quantile 0.99)

print(f"\n=== RUN B : Top {TOP_PERCENT}% de chaque indicateur ===\n")
print(f"  {'Indicateur':<15} {'n_top':>7}  {'rho':>8}")
print(f"  {'-'*35}")

results_b = []
for m in METRICS:
    sub      = df[["year_entry", m]].dropna()
    cutoff   = sub[m].quantile(threshold)    # Calcul de la valeur seuil du top 1%
    sub_top  = sub[sub[m] >= cutoff]         # Filtrage des données

    rho, direction = run_spearman(sub_top, m)
    print(f"  {m:<15} {len(sub_top):>7}  {rho:>8.4f}")
    results_b.append({
        "run": f"top{TOP_PERCENT}pct", "indicateur": m,
        "n": len(sub_top), "rho": round(rho, 4), "direction": direction
    })

# Création d'une grille de graphiques : 2 lignes (Global vs Top) x 4 colonnes (Les métriques)
fig, axes = plt.subplots(2, len(METRICS), figsize=(5 * len(METRICS), 10))
fig.suptitle(
    f"Année d'entrée LCC vs centralité\n"
    f"Haut : population complète  |  Bas : top {TOP_PERCENT}%",
    fontsize=13
)

for idx, m in enumerate(METRICS):
    ra = results_a[idx]
    rb = results_b[idx]

    sub     = df[["year_entry", m]].dropna()
    cutoff  = sub[m].quantile(threshold)
    sub_top = sub[sub[m] >= cutoff]

    # --- Ligne du haut : Graphique Population Complète ---
    ax = axes[0][idx]
    ax.scatter(sub["year_entry"], sub[m], alpha=0.15, s=8, color="#2C3E50") # Nuage de points transparent
    ax.axhline(cutoff, color="#E63946", linewidth=1, linestyle="--", label=f"seuil top {TOP_PERCENT}%")
    ax.set_xlabel("Année d'entrée")
    ax.set_ylabel(m.capitalize())
    ax.set_title(f"{m.capitalize()} — complet\nρ = {ra['rho']:.3f}")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.2)

    # --- Ligne du bas : Graphique Top 1% ---
    ax = axes[1][idx]
    ax.scatter(sub_top["year_entry"], sub_top[m], alpha=0.3, s=10, color="#E63946")
    ax.set_xlabel("Année d'entrée")
    ax.set_ylabel(m.capitalize())
    ax.set_title(f"{m.capitalize()} — top {TOP_PERCENT}%\nρ = {rb['rho']:.3f}")
    ax.grid(alpha=0.2)

plt.tight_layout()
fig.savefig(str(OUTPUT_DIR / "scatter_spearman.png"), dpi=200, bbox_inches="tight")
plt.close(fig)
print(f"\n→ scatter_spearman.png sauvegardé")

df_res = pd.DataFrame(results_a + results_b)
df_res.to_csv(OUTPUT_DIR / "resultats_spearman.csv", index=False)

# Affichage propre des résultats finaux dans la console de commande
print(f"── Run A : population complète")
df_a = pd.DataFrame(results_a)
print(df_a[["indicateur", "n", "rho"]].to_string(index=False))
print(f"\n── Run B : top {TOP_PERCENT}%")
df_b = pd.DataFrame(results_b)
print(df_b[["indicateur", "n", "rho"]].to_string(index=False))
print(f"Sorties : {OUTPUT_DIR}")
