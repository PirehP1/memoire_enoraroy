library(mongolite)
library(dplyr)
library(tidyr)
library(zoo)
library(xtable)

#calcul la distribution temporelle des langues de publication parmi les 6 langues dominantes du corpus
#si le choix du top6 est sur toute la période, pouvant masquer des langues qui étaient dominantes en proportion à un moment
#nous avons pu constater au cours de notre projet que les langues dominantes changent pas, ou peu
mongo_config <- list(
  url = "mongodb://localhost:27017/",
  db = "nom_de_la_base"
)

collection_url <- paste0(mongo_config$url, mongo_config$db)

references <- mongo(collection = "collection_mongo", url = collection_url)

df_raw <- references$find(
  query = '{}',
  fields = '{"year": 1, "language": 1}'
)

references$disconnect()

years_key <- c(1980, 2000, 2020)


df <- df_raw %>%
  as_tibble() %>%
  mutate(
    year = as.numeric(year),
    language = ifelse(is.na(language) | language == "" | language == "none",
                      "Unknown", language)
  ) %>%
  filter(!is.na(year), year > 0, language != "Unknown")

# ---------------------------------------------------------
# 3. TOP 6 LANGUES
# ---------------------------------------------------------
top6 <- df %>%
  count(language, sort = TRUE) %>%
  slice(1:6) %>%
  pull(language)

df <- df %>% filter(language %in% top6)

# ---------------------------------------------------------
# 4. PARTS ANNUELLES
# ---------------------------------------------------------
df_year <- df %>%
  group_by(year, language) %>%
  summarise(n = n(), .groups = "drop") %>%
  complete(year = seq(min(year), max(year)),
           language,
           fill = list(n = 0)) %>%
  group_by(year) %>%
  mutate(share = n / sum(n)) %>%
  ungroup()


df_smooth <- df_year %>%
  arrange(language, year) %>%
  group_by(language) %>%
  mutate(
    share_smooth = zoo::rollmean(share, k = 5, fill = NA, align = "center")
  ) %>%
  ungroup()


summary_points <- df_smooth %>%
  filter(year %in% years_key) %>%
  select(year, language, share_smooth) %>%
  mutate(share_pct = round(share_smooth * 100, 1))

print(summary_points)
print(xtable(summary_points), file = "table_langues.tex", include.rownames = FALSE)
