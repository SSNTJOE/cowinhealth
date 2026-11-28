-- Long-text recipe i18n (plain text fields — not HTML/JSON in current catalog).
-- Keep title columns on catalog_recipes: name_zh / name_en / name_ja / name_ko.
-- Detail/list APIs: COALESCE(NULLIF(tr.col,''), r.col).

CREATE TABLE IF NOT EXISTS recipe_translations (
  recipe_id INT NOT NULL,
  lang VARCHAR(8) NOT NULL,
  recipe MEDIUMTEXT NULL,
  method MEDIUMTEXT NULL,
  benefit TEXT NULL,
  ban TEXT NULL,
  allergens TEXT NULL,
  nutrient TEXT NULL,
  source_hash VARCHAR(64) NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (recipe_id, lang),
  CONSTRAINT fk_recipe_tr_recipe
    FOREIGN KEY (recipe_id) REFERENCES catalog_recipes(recipe_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Special-disease + allergen display labels (canonical value = name_zh).
CREATE TABLE IF NOT EXISTS catalog_health_labels (
  label_id INT AUTO_INCREMENT PRIMARY KEY,
  kind ENUM('condition','allergen') NOT NULL,
  name_zh VARCHAR(128) NOT NULL,
  name_en VARCHAR(255) NULL,
  name_ja VARCHAR(255) NULL,
  name_ko VARCHAR(255) NULL,
  sort_order INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_health_labels_kind_zh (kind, name_zh),
  INDEX idx_health_labels_kind (kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
