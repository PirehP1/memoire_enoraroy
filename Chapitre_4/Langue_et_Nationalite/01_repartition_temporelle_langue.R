library(mongolite)
library(dplyr)
library(tidyr)
library(ggplot2)
library(zoo)
library(scales)


OUTPUT_DIR <- "chemin_destination"
if (!dir.exists(OUTPUT_DIR)) dir.create(OUTPUT_DIR, recursive = TRUE)

mongo_config <- list(
  url = "mongodb://localhost:27017/",
  db = "nom_de_la_base"
)

collection_url <- paste0(mongo_config$url, mongo_config$db)
references <- mongo(collection = "collection_mongo", url = collection_url)

df_raw <- references$find(
  query = '{}',
  fields = '{"id": 1, "year": 1, "language_name": 1}'
)

references$disconnect()

cat("Documents extraits:", nrow(df_raw), "\n")

df <- df_raw %>%
  as_tibble() %>%
  mutate(
    year = as.numeric(year),
    language_name = ifelse(is.na(language_name) | language_name == '' | language_name == 'none', "Unknown", language_name)
  ) %>%
  filter(
    !is.na(year),
    year > 0,
    language_name != "Unknown"
  )

cat("Documents après nettoyage:", nrow(df), "\n")
cat("Période couverte:", min(df$year, na.rm = TRUE), "-", max(df$year, na.rm = TRUE), "\n")

# ---------------------------------------------------------
# Fonction de génération par période
# ---------------------------------------------------------
generate_viz_period <- function(period_name, start_year, end_year) {
  
  dfp <- df %>% filter(year >= start_year, year <= end_year)
  n_total_p <- nrow(dfp)
  
  cat("  Documents dans la période:", n_total_p, "\n")
  
  # ---------------------------------------------------------
  # TOP langues + regroupement autres
  # ---------------------------------------------------------
  lang_stats <- dfp %>%
    group_by(language_name) %>%
    summarise(total_n = n(), .groups = "drop") %>%
    arrange(desc(total_n)) %>%
    slice(1:6)
  
  top_langs <- lang_stats$language_name
  
  dfp <- dfp %>%
    mutate(language_name = ifelse(language_name %in% top_langs, language_name, "Autre"))
  
  lang_stats <- dfp %>%
    group_by(language_name) %>%
    summarise(total_n = n(), .groups = "drop") %>%
    arrange(desc(total_n))
  
  lang_stats <- lang_stats %>%
    mutate(legend_label = paste0(language_name, " (n=", format(total_n, big.mark=" "), ")"))
  
  all_langs <- lang_stats$language_name
  
  cat("  Langues affichées:", paste(all_langs, collapse = ", "), "\n")
  
  legend_map <- setNames(lang_stats$legend_label, lang_stats$language_name)
  
  colors <- setNames(
    c("#E69F00","#56B4E9","#009E73","#F0E442","#0072B2","#999999", "#D55E00")[1:length(all_langs)],
    all_langs #ici, l'ordre des couleurs importe. Pour ma part, le "other" étant plus nb que la dernière langue du top6, je le souhaitais en gris
  )
  
    df_time <- dfp %>%
    group_by(year, language_name) %>%
    summarise(n_year = n(), .groups = "drop") %>%
    complete(year = start_year:end_year, language_name, fill = list(n_year = 0)) %>%
    group_by(year) %>%
    mutate(prop = n_year / sum(n_year)) %>%
    ungroup()
  
  # ---------------------------------------------------------
  # GRAPH 1 : proportions
  # ---------------------------------------------------------
  p_freq <- ggplot(df_time, aes(x = year, y = prop, fill = language_name)) +
    geom_bar(stat = "identity", position = "stack", width = 0.9, color = "white", linewidth = 0.01) +
    scale_fill_manual(values = colors, labels = legend_map) +
    scale_y_continuous(labels = percent) +
    scale_x_continuous(breaks = seq(start_year, end_year, by = 10)) +
    labs(
      title = paste("Évolution des Proportions par Langue -", period_name),
      subtitle = paste("Effectif total de la période N =", format(n_total_p, big.mark=" ")),
      x = "Année",
      y = "Fréquence relative",
      fill = "Langue"
    ) +
    theme_minimal() +
    theme(legend.position = "bottom")
  
  # ---------------------------------------------------------
  # GRAPH 2 : occurrences
  # ---------------------------------------------------------
  p_occ <- ggplot(df_time, aes(x = year, y = n_year, fill = language_name)) +
    geom_bar(stat = "identity", position = "stack", width = 0.9, color = "white", linewidth = 0.01) +
    scale_fill_manual(values = colors, labels = legend_map) +
    scale_x_continuous(breaks = seq(start_year, end_year, by = 10)) +
    labs(
      title = paste("Évolution des Volumes par Langue -", period_name),
      subtitle = paste("Effectif total de la période N =", format(n_total_p, big.mark=" ")),
      x = "Année",
      y = "Nombre d'occurrences",
      fill = "Langue"
    ) +
    theme_minimal() +
    theme(legend.position = "bottom")
  
  freq_file <- file.path(OUTPUT_DIR, paste0("Stackbar_Freq_", period_name, "_mongo.pdf"))
  occ_file <- file.path(OUTPUT_DIR, paste0("Stackbar_Occ_", period_name, "_mongo.pdf"))
  
  ggsave(freq_file, p_freq, width=12, height=7, device = cairo_pdf)
  ggsave(occ_file, p_occ, width=12, height=7, device = cairo_pdf)
  
  cat("Sauvegardé:", basename(freq_file), "\n")
  cat("Sauvegardé:", basename(occ_file), "\n")
}


generate_viz_period("1975_2025", 1975, 2025)
