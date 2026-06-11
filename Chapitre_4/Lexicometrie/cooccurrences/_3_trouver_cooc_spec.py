"""
Script permettant de lire la matrice creuse produite par le protocole ici : https://github.com/SLamasse/matcoocs

et extraire les cooccurrences spécifiques des termes dans la liste 'LEMMES'
utile pour contextualiser les mots / sémantiser les vocabulaires (par ex ceux sortis par l'AFC)
de sorte à ne pas reposer sur une unique concordance

"""



import numpy as np
import scipy.sparse as sp

LEMMES = ["duke",
"patrician",
"rector",
"count"
]  
SEUIL  = 1.5
MODE   = "positif"   # "positif" ou "négatif"
TOP_N  = 20        # ex: 20, ou None pour tout garder

def extraire_et_sauvegarder(fichier_matrice, fichier_vocabulaire, lemme, seuil, mode, top_n):
    try:
        words = np.load(fichier_vocabulaire, allow_pickle=True)['words'].tolist()
        data_spec = np.load(fichier_matrice, allow_pickle=True)
        matrice = sp.csr_matrix(
            (data_spec['data'], data_spec['indices'], data_spec['indptr']),
            shape=tuple(data_spec['shape'])
        )

        if lemme not in words:
            print(f"  ✗ '{lemme}' introuvable.")
            return

        idx = words.index(lemme)
        colonne = matrice[:, idx].toarray().flatten()

        if mode == 'positif':
            resultats = [(words[i], float(colonne[i])) for i in range(len(words)) if colonne[i] >= seuil and i != idx]
            resultats.sort(key=lambda x: x[1], reverse=True)
        else:
            resultats = [(words[i], float(colonne[i])) for i in range(len(words)) if colonne[i] <= -seuil and i != idx]
            resultats.sort(key=lambda x: x[1])

        if top_n:
            resultats = resultats[:top_n]

        fichier_sortie = f"resultats_{lemme}_{mode}.txt"
        with open(fichier_sortie, 'w', encoding='utf-8') as f:
            f.write(f"Lemme: {lemme} | Mode: {mode} | Seuil: {seuil}\n")
            for mot, score in resultats:
                f.write(f"{mot}: {score:.4f}\n")

        print(f"  ✓ '{lemme}' : {len(resultats)} termes → {fichier_sortie}")

    except Exception as e:
        print(f"  ✗ '{lemme}' : Erreur — {e}")


print(f"Traitement de {len(LEMMES)} terme(s)...\n")
for lemme in LEMMES:
    extraire_et_sauvegarder(
        'Results/matrix_specificity.npz',
        'Results/matrix_general.npz',
        lemme, SEUIL, MODE, TOP_N
    )
print("\nTerminé.")
