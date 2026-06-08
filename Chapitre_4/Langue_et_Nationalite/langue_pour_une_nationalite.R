library(mongolite)
library(tidyverse)
library(xtable)

#le but de ce script est, pour une nationalité donnée, de visualiser et quantifier la langue de publication
#la plus employée (ou les plus employées) au cours du temps (attention toutefois, car un polonais + 20 américains sur une publication compte quand même pour un polonais)
#L'inspiration de ce programme vient du constat que, sur le graphe d'anglicisation, la faible part des polonais publiant en anglais
#m'est apparue étonnante (car je m'attendais à ce que les polonais écrivent immédiatement en anglais)
#bien entendu, n'importe quelle nationalité peut être considérée. Toutefois, nous laissons ici l'exemple de la Pologne car il produit
#des résultats particulièrement intéressants


# Abscisses : années | Ordonnées : langues | Couleur : fréquence relative
# ─────────────────────────────────────────────────────────────────────────────

OUTPUT_DIR <- "chemin_fichier"
if (!dir.exists(OUTPUT_DIR)) dir.create(OUTPUT_DIR, recursive = TRUE)

PAYS_CIBLE <- "Poland" #ou toute autre nationalité que l'on souhaite étudier

# Seuil minimal : on n'affiche que les langues représentant au moins X% des
# publications sur l'ensemble de la période (évite le bruit)
SEUIL_LANGUE_PCT <- 0.5

# ─────────────────────────────────────────────────────────────────────────────
# Extraction MongoDB
# ─────────────────────────────────────────────────────────────────────────────

con_auth <- mongo(collection = "authors", db = "references_biblio_mongo")
df_authors_raw <- con_auth$find(fields = '{"cle": 1, "nationalites": 1}')
con_auth$disconnect()

con_refs <- mongo(collection = "references", db = "references_biblio_mongo")
df_refs_raw <- con_refs$find(
  query  = '{"auteurs": {"$exists": true, "$ne": []}}',
  fields = '{"_id": 1, "auteurs": 1, "language_name": 1, "year": 1}'
)
con_refs$disconnect()

cat("Auteurs extraits    :", nrow(df_authors_raw), "\n")
cat("Références extraites:", nrow(df_refs_raw), "\n")

auteurs_polonais <- df_authors_raw %>%
  as_tibble() %>%
  filter(!map_lgl(nationalites, is.null), !map_lgl(nationalites, ~ length(.) == 0)) %>%
  unnest(nationalites) %>%
  filter(nom_pays == PAYS_CIBLE) %>%
  dplyr::select(cle) %>%
  distinct()

cat("Auteurs polonais identifiés:", nrow(auteurs_polonais), "\n")

# ─────────────────────────────────────────────────────────────────────────────
# Références des auteurs polonais
# ─────────────────────────────────────────────────────────────────────────────

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

# Jointure : on garde uniquement les publications avec au moins un auteur polonais
df_polonais <- refs_clean %>%
  inner_join(auteurs_polonais, by = "cle") %>%
  distinct(id_ref, language_name, year)   # une publication compte une fois même si
# plusieurs auteurs polonais la co-signent

cat("Publications avec auteur(s) polonais:", nrow(df_polonais), "\n")

# ─────────────────────────────────────────────────────────────────────────────
# Filtrage des langues trop rares (bruit)
# ─────────────────────────────────────────────────────────────────────────────

langues_retenues <- df_polonais %>%
  count(language_name, sort = TRUE) %>%
  mutate(pct = n / sum(n) * 100) %>%
  filter(pct >= SEUIL_LANGUE_PCT) %>%
  pull(language_name)

cat("Langues retenues (>=", SEUIL_LANGUE_PCT, "%) :",
    paste(langues_retenues, collapse = ", "), "\n")

# ─────────────────────────────────────────────────────────────────────────────
# Agrégation : fréquence relative par langue et par année
# ─────────────────────────────────────────────────────────────────────────────

df_heatmap <- df_polonais %>%
  mutate(language_name = ifelse(language_name %in% langues_retenues,
                                language_name, "Other")) %>%
  group_by(year, language_name) %>%
  summarise(n_pub = n(), .groups = "drop") %>%
  complete(year = 1975:2025, language_name, fill = list(n_pub = 0)) %>%
  group_by(year) %>%
  mutate(
    total_year = sum(n_pub),
    pct        = ifelse(total_year > 0, n_pub / total_year * 100, NA_real_)
  ) %>%
  ungroup()

# Ordre des langues : English en haut, puis par fréquence globale décroissante
ordre_langues <- df_heatmap %>%
  group_by(language_name) %>%
  summarise(total = sum(n_pub, na.rm = TRUE)) %>%
  arrange(desc(total)) %>%
  pull(language_name)

# English forcé en premier si présent
if ("English" %in% ordre_langues) {
  ordre_langues <- c("English", setdiff(ordre_langues, "English"))
}

df_heatmap <- df_heatmap %>%
  mutate(language_name = factor(language_name, levels = rev(ordre_langues)))

# ─────────────────────────────────────────────────────────────────────────────
# GRAPHIQUE 1 : Heatmap fréquence relative (% de l'année)
# ─────────────────────────────────────────────────────────────────────────────

# On masque les cases où aucune publication cette année-là (total_year == 0)
df_heatmap_plot <- df_heatmap %>%
  mutate(pct_display = ifelse(total_year == 0, NA_real_, pct))

p_heatmap_pct <- ggplot(df_heatmap_plot,
                        aes(x = year, y = language_name, fill = pct_display)) +
  geom_tile(color = "white", linewidth = 0.3) +
  scale_fill_gradient(
    low      = "#f7fbff",
    high     = "#08306b",
    na.value = "grey90",
    name     = "% de l'année",
    labels   = function(x) paste0(round(x), "%")
  ) +
  scale_x_continuous(breaks = seq(1975, 2025, 5)) +
  labs(
    title    = "Distribution des langues de publication des auteurs polonais (1975–2025)",
    subtitle = paste0(
      "Fréquence relative annuelle — une publication compte une fois même si plusieurs auteurs polonais la co-signent\n",
      "Langues affichées : >= ", SEUIL_LANGUE_PCT, "% des publications sur l'ensemble de la période"
    ),
    x       = "Année de publication",
    y       = "Langue",
    caption = paste0("N total = ", nrow(df_polonais),
                     " publications | Source : WorldCat, corpus médiévistique 1975-2025")
  ) +
  theme_minimal() +
  theme(
    plot.title       = element_text(size = 13, face = "bold"),
    plot.subtitle    = element_text(size = 9, color = "gray40"),
    plot.caption     = element_text(size = 8, hjust = 0, face = "italic"),
    axis.text.x      = element_text(angle = 45, hjust = 1, size = 9),
    axis.text.y      = element_text(size = 10),
    axis.title       = element_text(size = 11),
    panel.grid       = element_blank(),
    legend.position  = "right",
    legend.key.height = unit(1.5, "cm")
  )

ggsave(
  paste0(OUTPUT_DIR, "heatmap_langues_polonais_pct.pdf"),
  p_heatmap_pct,
  width = 18, height = 7,
  device = cairo_pdf
)
cat("✓ Heatmap (%) sauvegardée\n")

# ─────────────────────────────────────────────────────────────────────────────
# GRAPHIQUE 2 : Heatmap volume brut (n publications)
# Permet de voir si les faibles % correspondent à de faibles effectifs absolus
# ─────────────────────────────────────────────────────────────────────────────

p_heatmap_n <- ggplot(df_heatmap_plot,
                      aes(x = year, y = language_name, fill = n_pub)) +
  geom_tile(color = "white", linewidth = 0.3) +
  scale_fill_gradient(
    low      = "#fff5f0",
    high     = "#a50f15",
    na.value = "grey90",
    name     = "n publications"
  ) +
  scale_x_continuous(breaks = seq(1975, 2025, 5)) +
  labs(
    title    = "Volume brut des publications des auteurs polonais par langue (1975–2025)",
    subtitle = paste0(
      "Nombre absolu de publications — complément de la heatmap en fréquence relative\n",
      "Langues affichées : >= ", SEUIL_LANGUE_PCT, "% des publications sur l'ensemble de la période"
    ),
    x       = "Année de publication",
    y       = "Langue",
    caption = paste0("N total = ", nrow(df_polonais),
                     " publications | Source : WorldCat, corpus médiévistique 1975-2025")
  ) +
  theme_minimal() +
  theme(
    plot.title       = element_text(size = 13, face = "bold"),
    plot.subtitle    = element_text(size = 9, color = "gray40"),
    plot.caption     = element_text(size = 8, hjust = 0, face = "italic"),
    axis.text.x      = element_text(angle = 45, hjust = 1, size = 9),
    axis.text.y      = element_text(size = 10),
    axis.title       = element_text(size = 11),
    panel.grid       = element_blank(),
    legend.position  = "right",
    legend.key.height = unit(1.5, "cm")
  )

ggsave(
  paste0(OUTPUT_DIR, "heatmap_langues_polonais_n.pdf"),
  p_heatmap_n,
  width = 18, height = 7,
  device = cairo_pdf
)
cat("✓ Heatmap (n) sauvegardée\n")

# ─────────────────────────────────────────────────────────────────────────────
# Tableau récapitulatif : distribution par décennie — export LaTeX
# ─────────────────────────────────────────────────────────────────────────────

df_decade <- df_polonais %>%
  mutate(
    decade        = paste0(floor(year / 10) * 10, "s"),
    language_name = ifelse(language_name %in% langues_retenues,
                           language_name, "Other")
  ) %>%
  group_by(decade, language_name) %>%
  summarise(n = n(), .groups = "drop") %>%
  group_by(decade) %>%
  mutate(pct = round(n / sum(n) * 100, 1)) %>%
  ungroup() %>%
  mutate(cell = paste0(n, " (", pct, "%)")) %>%
  dplyr::select(decade, language_name, cell) %>%
  pivot_wider(names_from = decade, values_from = cell, values_fill = "0 (0%)")

sink(paste0(OUTPUT_DIR, "table_langues_polonais_decennie.tex"))
print(
  xtable(
    df_decade,
    caption = "Distribution des langues de publication des auteurs polonais par décennie (n et \\%)",
    label   = "tab:langues_polonais_decennie"
  ),
  include.rownames  = FALSE,
  caption.placement = "top",
  sanitize.text.function = identity
)
sink()

cat("\n=== Terminé. Fichiers dans:", OUTPUT_DIR, "===\n")