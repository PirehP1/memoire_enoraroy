
## Objectif : mesurer le flux annuel de nouveaux entrants dans
## le corpus par groupe de nationalité, agrégé par décennie,
## afin d'observer les reconfigurations de la structure nationale
## du champ sur la période 1975-2025.
## Concept de « nouveau auteur » : un auteur est comptabilisé
## une seule fois, l'année de sa première publication recensée
## dans le corpus. Ce choix permet de distinguer le flux
## d'entrée dans le champ (dynamique) du volume
## brut de publications (activité des auteurs déjà présents).

library(mongolite)
library(tidyverse)
library(xtable)

con_refs    <- mongo(collection = "references", db = "references_biblio_mongo")
con_auteurs <- mongo(collection = "authors",    db = "references_biblio_mongo")

## Pour chaque auteur (identifié par sa clé), on extrait l'année
## de sa première publication dans le corpus (MIN sur l'ensemble
## des références auxquelles il contribue). Les observations hors
## de la fenêtre temporelle 1975-2025 sont écartées.
df_first_pub <- con_refs$find(fields = '{"auteurs.cle": 1, "year": 1}') %>%
  as_tibble() %>%
  unnest(auteurs) %>%
  mutate(year_num = as.numeric(year)) %>%
  group_by(cle) %>%
  summarise(first_year = min(year_num, na.rm = TRUE), .groups = "drop") %>%
  filter(is.finite(first_year), first_year >= 1975, first_year <= 2025)

## Récupération des nationalités déclarées pour chaque auteur.
## Un auteur peut posséder plusieurs nationalités (binationalité) :
## chaque nationalité est stockée comme une entrée distincte dans
## le tableau `nationalites`, ce que `unnest()` dénormalise ici.
df_nat_raw <- con_auteurs$find(fields = '{"cle": 1, "nationalites.nom_pays": 1}') %>%
  as_tibble() %>%
  unnest(nationalites, keep_empty = TRUE)

## ── 2. CONSTRUCTION DU TABLEAU AUTEUR × NATIONALITÉ ─────────

## Les auteurs pour lesquels aucune nationalité n'a pu être
## identifiée reçoivent la modalité « undetermined ». Cette
## catégorie est analytiquement significative : sa croissance
## sur la période reflète l'élargissement du champ à des
## espaces nationaux sous-représentés dans les répertoires
## biographiques exploités pour l'identification.
##
## Schème de pondération : pour neutraliser les effets de la
## binationalité sur les totaux, chaque auteur compte pour 1
## au total, son poids étant réparti à parts égales entre ses
## n nationalités (poids = 1/n). Un auteur mononational pèse
## donc 1 ; un binational pèse 0,5 dans chacun de ses groupes.
df_final <- left_join(df_first_pub, df_nat_raw, by = "cle") %>%
  mutate(nom_pays = ifelse(is.na(nom_pays), "undetermined", nom_pays)) %>%
  group_by(cle) %>%
  mutate(poids = 1 / n()) %>%
  ungroup()

## ── 3. REGROUPEMENT EN GROUPES ANALYTIQUES ──────────────────

## Les nationalités sont regroupées en cinq catégories :
## les sous-champs nationaux les plus représentés (US, UK, FR)
## sont isolés pour permettre la comparaison de leurs trajectoires ;
## la catégorie « Inconnu » (nationalité non identifiée) est
## maintenue comme observable à part entière ; toutes les autres
## nationalités sont agrégées dans « Autre ».
##
## ⚠ Les patterns grepl() ci-dessous supposent que nom_pays est
## stocké sous forme de label en français ou en anglais.
## Vérifier les valeurs détectées à l'exécution et ajuster si besoin.
pays_us <- unique(df_final$nom_pays[
  grepl("United States|États-Unis|Etats-Unis|USA|Américain|American",
        df_final$nom_pays, ignore.case = TRUE)
])
pays_uk <- unique(df_final$nom_pays[
  grepl("United Kingdom|Royaume-Uni|Britain|British",
        df_final$nom_pays, ignore.case = TRUE)
])
pays_fr <- unique(df_final$nom_pays[
  grepl("^France$|^French$|^Français$",
        df_final$nom_pays, ignore.case = TRUE)
])

cat("  US :", paste(pays_us, collapse = ", "), "\n")
cat("  UK :", paste(pays_uk, collapse = ", "), "\n")
cat("  FR :", paste(pays_fr, collapse = ", "), "\n\n")

df_stats <- df_final %>%
  mutate(
    groupe = case_when(
      nom_pays %in% pays_us      ~ "US",
      nom_pays %in% pays_uk      ~ "UK",
      nom_pays %in% pays_fr      ~ "FR",
      nom_pays == "undetermined" ~ "Inconnu",
      TRUE                       ~ "Autre"
    )
  )

## ── 4. CALCUL DES PARTS ANNUELLES ───────────────────────────

## Les parts sont calculées sur le total de l'ensemble des groupes
## (y compris « Autre » et « Inconnu »), de sorte que leur somme
## soit égale à 100 % pour chaque année. Le `complete()` garantit
## la présence de toutes les combinaisons année × groupe, y compris
## celles à effectif nul, évitant ainsi tout biais dans les totaux.
annuel_wide <- df_stats %>%
  group_by(first_year, groupe) %>%
  summarise(n = sum(poids), .groups = "drop") %>%
  complete(first_year, groupe, fill = list(n = 0)) %>%
  group_by(first_year) %>%
  mutate(total = sum(n), pct = n / total * 100) %>%
  ungroup()

## Vérification interne : la somme des parts doit être exactement
## 100 % pour chaque année (à la précision numérique près).
stopifnot(all(
  abs(annuel_wide %>%
        group_by(first_year) %>%
        summarise(s = sum(pct), .groups = "drop") %>%
        pull(s) - 100) < 1e-6
))

## ── 5. AGRÉGATION PAR DÉCENNIE ET EXPORT LATEX ──────────────

## L'agrégation décennale lisse la volatilité inhérente aux petits
## effectifs annuels, particulièrement sensible en début de période
## (années 1970-1980), et produit un tableau de taille exploitable.
## Les parts sont recalculées sur les effectifs décennaux agrégés,
## préservant ainsi la cohérence entre numérateurs et dénominateurs.
tab_latex <- annuel_wide %>%
  mutate(decennie = paste0(floor(first_year / 10) * 10, "s")) %>%
  group_by(decennie, groupe) %>%
  summarise(n = sum(n), .groups = "drop") %>%
  group_by(decennie) %>%
  mutate(pct = n / sum(n) * 100) %>%
  ungroup() %>%
  mutate(
    label  = sprintf("%.0f (%.1f\\%%)", round(n), pct),
    groupe = recode(groupe,
                    "US"      = "États-Unis",
                    "UK"      = "Royaume-Uni",
                    "FR"      = "France",
                    "Inconnu" = "Nat. inconnue",
                    "Autre"   = "Autre"
    )
  ) %>%
  select(groupe, decennie, label) %>%
  pivot_wider(names_from = decennie, values_from = label) %>%
  rename(Groupe = groupe)

print(
  xtable(
    tab_latex,
    caption = paste(
      "Flux de nouveaux auteurs par groupe de nationalité et décennie",
      "(effectif pondéré et part \\% du total des entrants)"
    ),
    label = "tab:flux_nouveaux_auteurs"
  ),
  include.rownames       = FALSE,
  booktabs               = TRUE,
  caption.placement      = "top",
  sanitize.text.function = identity,
  file                   = "tableau_flux_nouveaux_auteurs.tex"
)
cat("Tableau exporté → tableau_flux_nouveaux_auteurs.tex\n")
