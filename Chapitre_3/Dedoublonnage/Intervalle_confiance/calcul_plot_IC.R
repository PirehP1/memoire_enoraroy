# validation_dedoublonnage.R
# --------------------------
# Vérification visuelle du dédoublonnage semi-automatisé par encadrement :
# la courbe du dédoublonnage manuel doit se situer entre la base brute
# (borne haute) et la base dédoublonnée de manière agressive (borne basse).
# Aucune modélisation statistique n'est opérée ; la zone colorée entre les
# deux extrêmes sert uniquement de repère visuel.

packages <- c("RMariaDB", "dplyr", "ggplot2", "tidyr")
for (pkg in packages) {
  if (!require(pkg, character.only = TRUE, quietly = TRUE)) {
    install.packages(pkg, dependencies = TRUE)
    library(pkg, character.only = TRUE)
  }
}

query <- "
  SELECT year, COUNT(*) AS nb_refs
  FROM reference
  WHERE year IS NOT NULL
  GROUP BY year
  ORDER BY year
"

bases <- list(
  borne_haute      = "biblio_complet",       # base brute, sans dédoublonnage
  dedoublon_manuel = "references_biblio",    # notre dédoublonnage semi-automatisé
  borne_basse      = "biblio_sans_doublon"   # dédoublonnage agressif
)

data_list <- lapply(names(bases), function(nom) {
  con <- dbConnect(RMariaDB::MariaDB(), dbname = bases[[nom]],
                   host = "localhost", user = "root", password = "PASSWORD")
  on.exit(dbDisconnect(con))
  df <- dbGetQuery(con, query)
  colnames(df) <- c("year", nom)
  df
})

clean_year <- function(df) {
  df %>%
    mutate(year = as.integer(as.character(year))) %>%
    filter(!is.na(year), year >= 1975, year <= 2025)
}

data_complete <- Reduce(
  function(a, b) full_join(a, b, by = "year"),
  lapply(data_list, clean_year)
) %>%
  arrange(year) %>%
  replace_na(list(borne_haute = 0, dedoublon_manuel = 0, borne_basse = 0))

# Vérification : combien d'années le dédoublonnage manuel est-il bien encadré ?
data_complete <- data_complete %>%
  mutate(
    hors_bornes = dedoublon_manuel < borne_basse | dedoublon_manuel > borne_haute
  )

n_hors <- sum(data_complete$hors_bornes)
cat(sprintf("Années hors bornes : %d sur %d\n", n_hors, nrow(data_complete)))

if (n_hors > 0) {
  cat("Années concernées :\n")
  print(filter(data_complete, hors_bornes) %>%
          select(year, borne_haute, dedoublon_manuel, borne_basse))
}


couleurs <- c(
  "Base brute (borne haute)"        = "#E63946",
  "Dédoublonnage agressif (borne basse)" = "#2A9D8F",
  "Dédoublonnage manuel"            = "#9D4EDD"
)

p <- ggplot(data_complete, aes(x = year)) +
  geom_ribbon(aes(ymin = borne_basse, ymax = borne_haute),
              fill = "#87CEEB", alpha = 0.35) +
  geom_line(aes(y = borne_haute,      color = "Base brute (borne haute)"),
            linewidth = 1.2, linetype = "dashed") +
  geom_line(aes(y = borne_basse,      color = "Dédoublonnage agressif (borne basse)"),
            linewidth = 1.2, linetype = "dashed") +
  geom_line(aes(y = dedoublon_manuel, color = "Dédoublonnage manuel"),
            linewidth = 1.8) +
  geom_point(aes(y = dedoublon_manuel, color = "Dédoublonnage manuel"),
             size = 3) +
  # Signalement des années hors bornes, s'il y en a
  geom_point(data = filter(data_complete, hors_bornes),
             aes(y = dedoublon_manuel),
             color = "#FF3333", size = 5, shape = 1, stroke = 2.5) +
  scale_color_manual(values = couleurs) +
  scale_x_continuous(breaks = seq(1975, 2025, by = 5), limits = c(1975, 2025)) +
  labs(
    title    = "Validation du dédoublonnage par encadrement (1975-2025)",
    subtitle = "Zone bleue : espace entre la base brute et le dédoublonnage agressif",
    x = "Année", y = "Nombre de références", color = NULL
  ) +
  theme_minimal() +
  theme(
    legend.position  = "bottom",
    plot.title       = element_text(face = "bold", size = 14),
    plot.subtitle    = element_text(size = 11),
    axis.text.x      = element_text(angle = 45, hjust = 1, size = 10),
    panel.grid.minor = element_line(color = "gray90")
  )

print(p)
ggsave("validation_dedoublonnage_1975-2025.png", p, width = 14, height = 8, dpi = 300)
