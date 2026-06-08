library(mongolite)
library(tidyverse)
library(xtable)

# Note bibliographique : l'idée de faire varier l'épaisseur du trait selon un volume
# s'inspire de Charles Minard (1869), qui faisait varier l'épaisseur selon les pertes
# humaines lors de la campagne de Russie de Napoléon.

#but = Mesurer l’évolution annuelle de la part des publications en anglais
#par nationalité d’auteur (Top 6), entre 1975 et 2025, en pondérant visuellement
# les trajectoires par le volume de production.

#NOTE IMPORTANTE : les auteurs binationaux sont comptés une fois pour chaque nationalité !

OUTPUT_DIR <- "chemin_destination"
PAYS_ANGLOPHONES <- c("United States of America", "United Kingdom", "Australia")

con_auth <- mongo(collection = "auteurs", db = "references_biblio_mongo")
df_authors_raw <- con_auth$find(fields = '{"cle": 1, "nationalites": 1}')
con_auth$disconnect()
#on filtre immédiatement toutes les références sans auteurs!!
con_refs <- mongo(collection = "collection_mongo", db = "nom_de_la_base")
df_refs_raw <- con_refs$find(
  query  = '{"auteurs": {"$exists": true, "$ne": []}}',
  fields = '{"_id": 1, "auteurs": 1, "language": 1, "year": 1}'
)
con_refs$disconnect()

#un auteur a 1 à N nationalités, et on exclut ensuite toutes les lignes des pays anglophones définis
#plus haut dans la variable
authors_clean <- df_authors_raw %>%
  as_tibble() %>%
  filter(!map_lgl(nationalites, is.null), !map_lgl(nationalites, ~ length(.) == 0)) %>%
  unnest(nationalites) %>%
  mutate(pays_nom = nom_pays) %>%
  filter(!pays_nom %in% PAYS_ANGLOPHONES) %>%
  dplyr::select(cle, pays_nom) %>%
  distinct() #on dédoublonne les nationalités au cas où y'aurait des pb de données
#mais un auteur binational compte tjrs deux fois (car une fois par pays)

#on nettoie les références, exclusion des langues vides
#et on déplie les auteurs de sorte à pouvoir faire la jointure
#bref, on conserve uniquement les publications dont au moins un auteur n'a pas qu'une nationalité anglophone
#définie au dessus
refs_clean <- df_refs_raw %>%
  as_tibble() %>%
  mutate(
    id_ref = as.character(`_id`),
    year   = as.numeric(as.character(year))
  ) %>%
  filter(!is.na(year), year >= 1975, year <= 2025) %>%
  filter(!is.na(language), language != "", language != "none") %>%
  unnest(auteurs) %>%
  dplyr::select(id_ref, cle, language, year)

df_analyse <- refs_clean %>%
  inner_join(authors_clean, by = "cle") %>%
  distinct(id_ref, pays_nom, language, year, .keep_all = TRUE)
#ATTENTION AU DISTINCT ICI
#une publication interna fr alle est comptée une fois pour la France et une fois pour l’Allemagne.
#donc c'est bien le volume de production associé au pays via participation auteur.

top_6_pays <- df_analyse %>%
  count(pays_nom, sort = TRUE) %>%
  head(6) %>% #ensuite on retient les pays ayant le plus de publication (ie les pays dont les nationaux sont le plus identifiés dans ma bdd)
  pull(pays_nom)

# ── Agrégation par pays × année ───────────────────────────────────────────────

#Nombre de références associées au pays p en année t
#et on compte le nb de ces références en anglais
df_evolution_anglais <- df_analyse %>%
  filter(pays_nom %in% top_6_pays) %>% #déjà on prend que les 6 principaux pays
  group_by(pays_nom, year) %>% #on agrège pays année pour compter le nb de références
  summarise( #nombre total de publications associées au pays p pour l’année t.
    total_pub     = n(),
    nb_anglais    = sum(grepl("^en$|^eng$|^english$",      language, ignore.case = TRUE), na.rm = TRUE),
    part_anglais  = (nb_anglais  / total_pub) * 100, #Parmi les publications associées au pays p en année t, quelle part est en anglais ? exprimé en pct
    .groups = "drop"
  ) #Un article co-signé par deux auteurs du même pays compte une seule fois (grâce au distinct en amont).



#MA sur trois ans pour éviter les gros pics
ma <- function(x, n = 3) stats::filter(x, rep(1/n, n), sides = 2)

PUISSANCE <- 3.6
#   La puissance amplifie de manière NON-LINÉAIRE les grandes valeurs du log,
#   pas les petites. Plus la puissance est élevée, plus l'écart entre
#   "beaucoup de publications" et "peu de publications" devient extrême
# -> mais du coup on fait une compression logarithmique PUIS une amplification par puissance. Les petits volumes restent faibles et les grands volumes sont fortement amplifiés

df_with_ma <- df_evolution_anglais %>%
  group_by(pays_nom) %>%
  arrange(year) %>%
  mutate(
    ma_anglais = as.numeric(ma(part_anglais, n = 3)),
    line_size = ((log10(total_pub))^PUISSANCE),
    point_size = line_size * 0.7
  ) %>%
  ungroup()

# ── Calcul des CUMULS 1975-1975 et 1975-2025 pour la légende ──────────────────
# CUMUL = somme de toutes les références publiées depuis 1975 jusqu'à l'année donnée

cumuls_par_pays <- df_evolution_anglais %>%
  group_by(pays_nom) %>%
  arrange(year) %>%
  mutate(cumul = cumsum(total_pub)) %>%
  ungroup()

# Extraire cumul en 1975 (= première année) et cumul en 2025 (= dernière année)
effectifs_cumules <- cumuls_par_pays %>%
  filter(year %in% c(1975, 2025)) %>%
  dplyr::select(pays_nom, year, cumul) %>%
  pivot_wider(names_from = year, values_from = cumul, names_prefix = "cumul_") %>%
  replace_na(list(cumul_1975 = 0, cumul_2025 = 0)) %>%
  mutate(
    label_avec_cumuls = sprintf("%s (n: %d → %d)", pays_nom, cumul_1975, cumul_2025)
  )

# Totaux cumulés globaux (top 6)
total_cumul_1975 <- cumuls_par_pays %>%
  filter(year == 1975) %>%
  summarise(total = sum(cumul, na.rm = TRUE)) %>%
  pull(total)

total_cumul_2025 <- cumuls_par_pays %>%
  filter(year == 2025) %>%
  summarise(total = sum(cumul, na.rm = TRUE)) %>%
  pull(total)

if (length(total_cumul_1975) == 0) total_cumul_1975 <- 0
if (length(total_cumul_2025) == 0) total_cumul_2025 <- 0

# Jointure pour avoir les labels avec cumuls
df_with_ma <- df_with_ma %>%
  left_join(effectifs_cumules %>% dplyr::select(pays_nom, label_avec_cumuls), by = "pays_nom") %>%
  mutate(pays_nom_display = label_avec_cumuls)

# ── Graphique ───────────────────────────────────────────────────────────────

#donc au total on a 4 dimensions
#position verticale étant la proportion en anglais
#épaisseur pour le volume de publications
#la couleur pour le pays
#les abcisses pour le temps
p_evolution <- ggplot(df_with_ma, aes(x = year, color = pays_nom_display, group = pays_nom)) +
  geom_line(
    aes(y = ma_anglais, linewidth = line_size),
    alpha = 0.8,
    lineend = "round"
  ) +
  scale_linewidth_identity() + 
  scale_x_continuous(breaks = seq(1975, 2025, 5)) +
  scale_y_continuous(limits = c(0, 100)) +
  labs(
    title    = "Évolution de la part de l'anglais (Top 6 des nationalités)",
    subtitle = paste(
      "Lignes : moyennes mobiles (3 ans)",
      "| Épaisseur : [log10(nb publications)]^3.7"
    ),
    x     = "Année",
    y     = "Part de publications en anglais (%)",
    color = "Pays",
    caption = sprintf("Total cumulé (top 6, 1975-2025) : n = %d → %d références", 
                      total_cumul_1975, total_cumul_2025)
  ) +
  theme_minimal() +
  theme(
    legend.position  = "right",
    legend.text      = element_text(size = 11),
    legend.title     = element_text(size = 12, face = "bold"),
    legend.key.size  = unit(1.2, "cm"),
    legend.key.width = unit(1.5, "cm"),
    plot.title       = element_text(size = 14, face = "bold"),
    plot.subtitle    = element_text(size = 9.5, color = "gray40"),
    plot.caption     = element_text(size = 9, hjust = 0, face = "italic"),
    axis.text.x      = element_text(angle = 45, hjust = 1),
    panel.grid.minor = element_blank()
  ) +
  guides(color = guide_legend(override.aes = list(linewidth = 2)))

ggsave(
  paste0(OUTPUT_DIR, "evolution_anglais_top6_par_annee.pdf"),
  p_evolution,
  width  = 16,
  height = 9
)

# ── Tableau de statistiques : export LaTeX ─────────────────────────────────────

stats_pays <- df_evolution_anglais %>%
  group_by(pays_nom) %>%
  summarise(
    part_anglais_moyenne = mean(part_anglais, na.rm = TRUE),
    part_anglais_min     = min(part_anglais,  na.rm = TRUE),
    part_anglais_max     = max(part_anglais,  na.rm = TRUE),
    nb_annees            = n()
  ) %>%
  arrange(desc(part_anglais_moyenne))

sink(paste0(OUTPUT_DIR, "stats_anglais_top6.tex"))
print(
  xtable(
    stats_pays,
    caption = "Statistiques de la part de l'anglais (Top 6 nationalités)",
    label   = "tab:stats_anglais",
    digits  = c(0, 0, 2, 2, 2, 0)
  ),
  include.rownames  = FALSE,
  caption.placement = "top"
)
sink()