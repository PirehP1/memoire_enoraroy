library(mongolite)
library(tidyverse)
library(xtable)
library(scales)

#distribution des nationalités des auteurs au moment de leur entrée dans la base -> cb de nouveaux auteurs (pondérés) apparaissent chaque année pour chaque pays
#ATTENTION ! exclusion volontaire de la nationalité la plus frq, Donc le “Top 6” est en réalité : rang 2 → rang 7 (pas le top 1)
#chaque auteur vaut 1 au total, réparti entre ses nationalités

con_refs <- mongo(collection = "references", db = "references_biblio_mongo")

df_first_pub <- con_refs$find(fields = '{"auteurs.cle": 1, "year": 1}') %>%
  as_tibble() %>%
  unnest(auteurs) %>%
  mutate(year_num = as.numeric(year)) %>%
  group_by(cle) %>%
  summarise(first_year = min(year_num, na.rm = TRUE), .groups = "drop") %>%
  filter(is.finite(first_year), first_year >= 1975, first_year <= 2025)

con_refs$disconnect()

con_auteurs <- mongo(collection = "authors", db = "references_biblio_mongo")
df_nat_raw <- con_auteurs$find(fields = '{"cle": 1, "nationalites.nom_pays": 1}') %>% 
  as_tibble() %>%
  unnest(nationalites, keep_empty = TRUE)

con_auteurs$disconnect()

# Jointure et calcul du poids (binationalité)
df_final <- left_join(df_first_pub, df_nat_raw, by = "cle") %>%
  mutate(nom_pays = ifelse(is.na(nom_pays), "Non identifié", nom_pays)) %>%
  group_by(cle) %>%
  mutate(poids = 1 / n()) %>%
  ungroup()


n_total_auteurs <- sum(df_final$poids)

# Extraction du Top 6
lang_stats <- df_final %>%
  group_by(nom_pays) %>%
  summarise(total_n = sum(poids), .groups = "drop") %>%
  filter(nom_pays != "Non identifié") %>%
  arrange(desc(total_n)) %>%
  slice(2:7)

top_pays <- lang_stats$nom_pays

# Regroupement
df_plot_prep <- df_final %>%
  mutate(pays_group = ifelse(nom_pays %in% top_pays | nom_pays == "Non identifié", nom_pays, "Autre"))

# Calcul des labels de légende avec effectifs formatés
legend_info <- df_plot_prep %>%
  group_by(pays_group) %>%
  summarise(total_n = sum(poids), .groups = "drop") %>%
  arrange(desc(total_n)) %>%
  mutate(legend_label = paste0(pays_group, " (n=", format(round(total_n, 0), big.mark=" "), ")"))

all_groups <- legend_info$pays_group
legend_map <- setNames(legend_info$legend_label, legend_info$pays_group)


colors <- setNames(
  c("lightgrey","darkgrey","#56B4E9","#F8766D","#F0E442","#00BFC4","#00BF7D", "darkorchid1","#FF69B4")[1:length(all_groups)],
  all_groups
)

# Agrégation par année pour le graphique
df_time <- df_plot_prep %>%
  group_by(first_year, pays_group) %>%
  summarise(count = sum(poids), .groups = "drop")


p_abs <- ggplot(df_time, aes(x = first_year, y = count, fill = pays_group)) +
  geom_bar(stat = "identity", position = "stack", width = 0.9, color = "white", linewidth = 0.01) +
  scale_fill_manual(values = colors, labels = legend_map) +
  scale_x_continuous(breaks = seq(1975, 2025, by = 5)) +
  labs(
    title = "Nationalité des nouveaux auteurs par année d'entrée",
    subtitle = paste("Effectif total pondéré N =", format(round(n_total_auteurs, 0), big.mark=" ")),
    x = "Année de première publication",
    y = "Nombre d'entrées (poids pondérés)",
    fill = "Nationalité"
  ) +
  theme_minimal() +
  theme(
    legend.position = "bottom",
    plot.title = element_text(face = "bold"),
    axis.text.x = element_text(angle = 45, hjust = 1)
  )

ggsave(
  filename = "nationalites_abs.pdf",
  plot = p_abs,
  device = cairo_pdf,
  width = 12,
  height = 7
)

# ---------------------------------------------------------
# 3 BIS. STACKED BAR 100% (PROPORTIONS PAR ANNÉE)
# ---------------------------------------------------------

df_time_100 <- df_time %>%
  group_by(first_year) %>%
  mutate(prop = count / sum(count)) %>%
  ungroup()

p_100 <- ggplot(df_time_100, aes(x = first_year, y = prop, fill = pays_group)) +
  geom_bar(
    stat = "identity",
    position = "stack",
    width = 0.9,
    color = "white",
    linewidth = 0.01
  ) +
  scale_fill_manual(values = colors, labels = legend_map) +
  scale_y_continuous(labels = percent_format(accuracy = 1)) +
  scale_x_continuous(breaks = seq(1975, 2025, by = 5)) +
  labs(
    title = "Part des nationalités des nouveaux auteurs par année",
    subtitle = "Stacked bar 100% (distribution normalisée par année)",
    x = "Année de première publication",
    y = "Part des entrées (%)",
    fill = "Nationalité"
  ) +
  theme_minimal() +
  theme(
    legend.position = "bottom",
    plot.title = element_text(face = "bold"),
    axis.text.x = element_text(angle = 45, hjust = 1)
  )

# ---------------------------------------------------------
# 4. EXPORT TABLEAU TEX
# ---------------------------------------------------------
df_table <- df_plot_prep %>%
  mutate(decennie = paste0((first_year %/% 10) * 10, "s")) %>%
  group_by(decennie, pays_group) %>%
  summarise(n = sum(poids), .groups = "drop") %>%
  pivot_wider(names_from = decennie, values_from = n, values_fill = 0) %>%
  mutate(across(where(is.numeric), ~ round(., 1)))

print(xtable(df_table, caption = "Nouveaux auteurs par nationalité et décennie"), include.rownames = FALSE)

ggsave(
  filename = "nationalites_100pct.pdf",
  plot = p_100,
  device = cairo_pdf,
  width = 12,
  height = 7
)
