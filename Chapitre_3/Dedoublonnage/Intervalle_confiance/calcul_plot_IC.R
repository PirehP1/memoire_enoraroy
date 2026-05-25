# Validation du dédoublonnage par intervalle de confiance (1975-2025)

try(detach("package:odbc", unload = TRUE), silent = TRUE)
try(detach("package:DBI", unload = TRUE), silent = TRUE)

packages <- c("RMariaDB", "dplyr", "ggplot2", "tidyr")
for (pkg in packages) {
  if (!require(pkg, character.only = TRUE, quietly = TRUE)) {
    install.packages(pkg, dependencies = TRUE)
    library(pkg, character.only = TRUE)
  }
}

# -----------------------------------------------------------------------------
# Connexion et extraction
# -----------------------------------------------------------------------------

query <- "SELECT year, COUNT(*) as nb_refs FROM reference WHERE year IS NOT NULL GROUP BY year ORDER BY year"

bases <- list(
  non_dedoublonne  = "biblio_complet",
  dedoublon_manuel = "references_biblio",
  sans_doublon     = "biblio_sans_doublon"
)

data_list <- lapply(names(bases), function(nom) {
  con <- dbConnect(RMariaDB::MariaDB(), dbname = bases[[nom]],
                   host = "localhost", user = "root", password = "PASSWORD")
  on.exit(dbDisconnect(con))
  df <- dbGetQuery(con, query)
  colnames(df) <- c("year", nom)
  df
})

# -----------------------------------------------------------------------------
# Nettoyage et fusion
# -----------------------------------------------------------------------------

clean_year <- function(df) {
  df %>%
    mutate(year = as.integer(as.character(year))) %>%
    filter(!is.na(year), year >= 1975, year <= 2025)
}

data_complete <- Reduce(function(a, b) full_join(a, b, by = "year"), 
                        lapply(data_list, clean_year)) %>%
  arrange(year) %>%
  replace_na(list(non_dedoublonne = 0, dedoublon_manuel = 0, sans_doublon = 0))


data_complete <- data_complete %>%
  mutate(
    # 1. Valeur centrale attendue (milieu exact entre les deux scénarios extrêmes)
    moyenne_estimee = (non_dedoublonne + sans_doublon) / 2,
    
    # 2. Proportion estimée de documents uniques conservés (p)
    # L'ajustement 'ifelse' évite une division par zéro si une année est vide
    p_estime        = moyenne_estimee / ifelse(non_dedoublonne == 0, 1, non_dedoublonne),
    
    # 3. Écart-type
    ecart_type      = sqrt(non_dedoublonne * p_estime * (1 - p_estime)),
    
    # 4. Calcul des bornes de l'intervalle à un niveau de confiance de 95%
    # (Seuil standard de 1.96 écart-type autour de la moyenne)
    ic_inf_95        = moyenne_estimee - 1.96 * ecart_type,
    ic_sup_95        = moyenne_estimee + 1.96 * ecart_type,
    
    # 5. Calcul des bornes de l'intervalle à un niveau de confiance de 99%
    # (Seuil plus conservateur de 2.576 écart-types autour de la moyenne)
    ic_inf_99        = moyenne_estimee - 2.576 * ecart_type,
    ic_sup_99        = moyenne_estimee + 2.576 * ecart_type,
    
    # 6. Tests d'appartenance : le dédoublonnage manuel est-il dans les clous ?
    dans_ic_95       = dedoublon_manuel >= ic_inf_95 & dedoublon_manuel <= ic_sup_95,
    dans_ic_99       = dedoublon_manuel >= ic_inf_99 & dedoublon_manuel <= ic_sup_99,
    
    # 7. Mesure de l'écart absolu à la moyenne estimée
    ecart_manuel_moyenne = dedoublon_manuel - moyenne_estimee
  )

taux_95 <- mean(data_complete$dans_ic_95) * 100
taux_99 <- mean(data_complete$dans_ic_99) * 100
cat(sprintf("Fiabilité IC 95%% : %.1f%%\n", taux_95))
cat(sprintf("Fiabilité IC 99%% : %.1f%%\n", taux_99))

# Isoler et lister les anomalies (les années hors de l'intervalle à 95%)
annees_hors_ic <- data_complete %>%
  filter(!dans_ic_95) %>%
  select(year, non_dedoublonne, dedoublon_manuel, sans_doublon, ic_inf_95, ic_sup_95)

# Affichage du tableau d'anomalies si au moins une année est rejetée
if (nrow(annees_hors_ic) > 0) {
  cat("\nAnnées hors IC 95% :\n")
  print(annees_hors_ic, row.names = FALSE)
}

# -----------------------------------------------------------------------------
# Graphique 1 — Vue d'ensemble
# -----------------------------------------------------------------------------

couleurs <- c(
  "Non dédoublonné"     = "#E63946",
  "Sans aucun doublon"  = "#2A9D8F",
  "Moyenne estimée"     = "#457B9D",
  "Dédoublonnage manuel" = "#9D4EDD"
)

p1 <- ggplot(data_complete, aes(x = year)) +
  geom_ribbon(aes(ymin = ic_inf_95, ymax = ic_sup_95), fill = "#87CEEB", alpha = 0.4) +
  geom_line(aes(y = non_dedoublonne,  color = "Non dédoublonné"),    linewidth = 1.3, linetype = "dashed") +
  geom_point(aes(y = non_dedoublonne, color = "Non dédoublonné"),    size = 2.5) +
  geom_line(aes(y = sans_doublon,     color = "Sans aucun doublon"), linewidth = 1.3, linetype = "dashed") +
  geom_point(aes(y = sans_doublon,    color = "Sans aucun doublon"), size = 2.5) +
  geom_line(aes(y = moyenne_estimee,  color = "Moyenne estimée"),    linewidth = 1.5) +
  geom_line(aes(y = dedoublon_manuel, color = "Dédoublonnage manuel"), linewidth = 1.8) +
  geom_point(aes(y = dedoublon_manuel, color = "Dédoublonnage manuel"), size = 3.5) +
  geom_point(data = filter(data_complete, !dans_ic_95),
             aes(y = dedoublon_manuel), color = "#FF3333", size = 5, shape = 1, stroke = 2.5) +
  scale_color_manual(values = couleurs) +
  scale_x_continuous(breaks = seq(1975, 2025, by = 5), limits = c(1975, 2025)) +
  labs(
    title    = "Validation du dédoublonnage manuel par intervalle de confiance (1975-2025)",
    subtitle = paste0("Zone bleue = IC 95% | Points cerclés = hors IC | Fiabilité : ", round(taux_95, 1), "%"),
    x = "Année", y = "Nombre de références", color = NULL
  ) +
  theme_minimal() +
  theme(
    legend.position  = "bottom",
    plot.title       = element_text(face = "bold", size = 15),
    plot.subtitle    = element_text(size = 11),
    axis.text.x      = element_text(angle = 45, hjust = 1, size = 10),
    panel.grid.minor = element_line(color = "gray90")
  )

print(p1)
ggsave("validation_dedoublonnage_1975-2025.png", p1, width = 14, height = 8, dpi = 300)

# Export

write.csv(data_complete, "resultats_analyse_dedoublonnage.csv", row.names = FALSE)
write.csv(
  data.frame(
    Indicateur = c("Années analysées", "Fiabilité IC 95%", "Fiabilité IC 99%",
                   "Années hors IC 95%", "Années hors IC 99%"),
    Valeur     = c(nrow(data_complete), paste0(round(taux_95, 1), "%"),
                   paste0(round(taux_99, 1), "%"),
                   sum(!data_complete$dans_ic_95), sum(!data_complete$dans_ic_99))
  ),
  "rapport_fiabilite.csv", row.names = FALSE
)