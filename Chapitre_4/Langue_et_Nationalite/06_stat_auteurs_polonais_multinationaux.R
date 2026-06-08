library(mongolite)
library(tidyverse)
library(xtable)

#le but de ce script est de tenter de comprendre si le fait que les polonais publient en français au début
#de la période est un effet de champ (au sens où le champ altimédiéviste aurait une localisation géographique, celle française)
#ou un effet du fait que ces auteurs sont multinationaux, et que l'une de leur nationalité est française (et vu le faible nombre d'auteurs,
#cela expliquerait peut être pourquoi ils publient en français et nuancerait notre constat)
#il s'agit bien d'un script exploratoire

OUTPUT_DIR <- "chemin_fichier"
if (!dir.exists(OUTPUT_DIR)) dir.create(OUTPUT_DIR, recursive = TRUE)

PAYS_CIBLE <- "Poland"
SEUIL_LANGUE_PCT <- 0.5

con_auth <- mongo(collection = "authors", db = "references_biblio_mongo")
df_authors_raw <- con_auth$find(fields = '{"cle": 1, "nationalites": 1}')
con_auth$disconnect()

con_refs <- mongo(collection = "references", db = "references_biblio_mongo")
df_refs_raw <- con_refs$find(
  query  = '{"auteurs": {"$exists": true, "$ne": []}}',
  fields = '{"_id": 1, "auteurs": 1, "language_name": 1, "year": 1}'
)
con_refs$disconnect()

cat("\n--- 1. EXTRACTION ---\n")
cat("Auteurs extraits      :", nrow(df_authors_raw), "\n")
cat("Références extraites  :", nrow(df_refs_raw), "\n")

# Filtrage : Auteurs polonais uniquement
auteurs_polonais <- df_authors_raw %>%
  as_tibble() %>%
  filter(!map_lgl(nationalites, is.null), !map_lgl(nationalites, ~ length(.) == 0)) %>%
  unnest(nationalites) %>%
  filter(nom_pays == PAYS_CIBLE) %>%
  dplyr::select(cle) %>%
  distinct()

cat("Auteurs polonais identifiés :", nrow(auteurs_polonais), "\n")

# Références des auteurs polonais
refs_clean <- df_refs_raw %>%
  as_tibble() %>%
  mutate(
    id_ref        = as.character(`_id`),
    year          = as.numeric(as.character(year)),
    language_name = ifelse(
      is.na(language_name) | language_name == "" | language_name == "none",
      "Unknown", language_name
    )
  ) %>%
  filter(!is.na(year), year >= 1975, year <= 2025) %>%
  filter(language_name != "Unknown") %>%
  unnest(auteurs) %>%
  dplyr::select(id_ref, cle, language_name, year)

# On GARDE la colonne 'cle' pour pouvoir faire les analyses sociologiques
df_polonais <- refs_clean %>%
  inner_join(auteurs_polonais, by = "cle") %>%
  dplyr::select(id_ref, cle, language_name, year)

cat("Relations Auteur-Publication polonaises :", nrow(df_polonais), "\n")

cat("\n--- 2. ANALYSE DE LA MULTINATIONALITE ---\n")

# A. Calcul du statut multinational par auteur
auteurs_stats <- df_authors_raw %>%
  as_tibble() %>%
  filter(cle %in% auteurs_polonais$cle) %>%
  mutate(is_multinational = map_lgl(nationalites, ~ length(unique(.x$nom_pays)) > 1)) %>%
  dplyr::select(cle, is_multinational)

# B. Taux de multinationalité par décennie
stats_multi_decennie <- df_polonais %>%
  mutate(decennie = paste0(floor(year / 10) * 10, "s")) %>%
  inner_join(auteurs_stats, by = "cle") %>%
  group_by(decennie) %>%
  summarise(
    nb_relations_auteurs_pub = n(),
    nb_auteurs_multi = sum(is_multinational, na.rm = TRUE),
    pct_multinational = round((nb_auteurs_multi / nb_relations_auteurs_pub) * 100, 1)
  )

print(stats_multi_decennie)

# Les "Autres" Nationalités
cat("\n--- 3. DETAILS DES AUTRES NATIONALITES (POUR BINATIONAUX) ---\n")

# Extraction des autres pays
details_multi <- df_authors_raw %>%
  as_tibble() %>%
  filter(cle %in% auteurs_polonais$cle) %>%
  mutate(pays_list = map(nationalites, ~ .x$nom_pays)) %>%
  filter(map_lgl(pays_list, ~ length(unique(.x)) > 1)) %>%
  mutate(autres_pays = map(pays_list, ~ setdiff(unique(.x), PAYS_CIBLE)))

# Croisement avec les décennies
pays_par_decennie <- df_polonais %>%
  mutate(decennie = paste0(floor(year / 10) * 10, "s")) %>%
  inner_join(details_multi, by = "cle") %>%
  unnest(autres_pays) %>%
  group_by(decennie, autres_pays) %>%
  summarise(n = n(), .groups = "drop") %>%
  arrange(decennie, desc(n))

print(pays_par_decennie, n = 20) 

# Préparation et Export du Tableau LaTeX (Langues de publication)
cat("\n--- 4. GENERATION DU TABLEAU LATEX ---\n")

# Dédoublonnage : on s'assure qu'une publication coécrite par 2 polonais ne compte qu'une fois pour la langue
df_polonais_unique <- df_polonais %>%
  distinct(id_ref, language_name, year)

# Filtrage des langues (bruit)
langues_retenues <- df_polonais_unique %>%
  count(language_name, sort = TRUE) %>%
  mutate(pct = n / sum(n) * 100) %>%
  filter(pct >= SEUIL_LANGUE_PCT) %>%
  pull(language_name)

df_table_final <- df_polonais_unique %>%
  mutate(decennie = paste0(floor(year / 10) * 10, "s")) %>%
  mutate(language_name = ifelse(language_name %in% langues_retenues, 
                                language_name, "Other")) %>%
  group_by(decennie, language_name) %>%
  summarise(n = n(), .groups = "drop") %>%
  group_by(decennie) %>%
  mutate(
    pct = (n / sum(n)) * 100,
    # On ajoute des doubles anti-slashs pour que LaTeX compile correctement les %
    label = paste0(n, " (", round(pct, 1), "\\%)") 
  ) %>%
  dplyr::select(language_name, decennie, label) %>%
  pivot_wider(names_from = decennie, values_from = label, values_fill = "0 (0\\%)")

# Affichage avec sanitize.text.function = identity pour ne pas casser les %
sink(paste0(OUTPUT_DIR, "langues_polonais_multinationaux_decennie.tex"))
print(xtable(df_table_final, 
             caption = "Distribution des langues de publication des auteurs polonais par décennie (n et \\%)",
             label = "tab:langues_polonais_decennie"), 
      include.rownames = FALSE,
      sanitize.text.function = identity)
sink()
