CREATE DATABASE IF NOT EXISTS healthing
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE healthing;

CREATE TABLE IF NOT EXISTS users (
  user_id VARCHAR(32) PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  nickname VARCHAR(64) NULL,
  birth_year INT NULL,
  height DECIMAL(5,1) NULL,
  weight DECIMAL(5,1) NULL,
  age INT NULL,
  gender VARCHAR(20) NULL,
  medical_history TEXT NULL,
  conditions_json TEXT NULL,
  allergies_json TEXT NULL,
  complexion_lab_json TEXT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_daily_activity (
  user_id VARCHAR(32) NOT NULL,
  activity_date DATE NOT NULL,
  actual_steps INT NOT NULL DEFAULT 0,
  burned_kcal DECIMAL(10,1) NULL,
  source VARCHAR(64) NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, activity_date),
  INDEX idx_user_activity_day (activity_date),
  CONSTRAINT fk_activity_user FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS health_records (
  record_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(32) NOT NULL,
  record_date DATETIME NOT NULL,
  symptoms TEXT NULL,
  discomfort TEXT NULL,
  face_color VARCHAR(255) NULL,
  lip_color VARCHAR(255) NULL,
  tongue_body_color VARCHAR(255) NULL,
  tongue_coat_color VARCHAR(255) NULL,
  heart_score INT NOT NULL,
  liver_score INT NOT NULL,
  spleen_score INT NOT NULL,
  lung_score INT NOT NULL,
  kidney_score INT NOT NULL,
  gallbladder_score INT NOT NULL,
  large_intestine_score INT NOT NULL,
  small_intestine_score INT NOT NULL,
  bladder_score INT NOT NULL,
  uterus_score INT NOT NULL,
  stomach_score INT NOT NULL DEFAULT 5,
  heart_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
  liver_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
  spleen_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
  lung_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
  kidney_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
  gallbladder_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
  large_intestine_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
  small_intestine_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
  bladder_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
  uterus_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
  stomach_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
  diet_advice VARCHAR(80) NULL,
  diet_url TEXT NULL,
  acupoint_url TEXT NULL,
  pulse_json TEXT NULL,
  face_grid_json TEXT NULL,
  face_measurements_json TEXT NULL,
  complexion_label VARCHAR(128) NULL,
  complexion_hex VARCHAR(16) NULL,
  complexion_hsv_json TEXT NULL,
  tongue_grid_json TEXT NULL,
  tongue_measurements_json TEXT NULL,
  organ_composite_json TEXT NULL,
  CONSTRAINT fk_health_user FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Online color calibration: per-shot features + EWMA running state (no GPU).
CREATE TABLE IF NOT EXISTS color_calib_samples (
  sample_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(32) NULL,
  record_id INT NULL,
  device_key VARCHAR(80) NULL,
  modality VARCHAR(16) NOT NULL,
  captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  cct_raw DOUBLE NULL,
  cct_used DOUBLE NULL,
  brightness_raw DOUBLE NULL,
  brightness_gain DOUBLE NULL,
  L DOUBLE NULL,
  a_star DOUBLE NULL,
  b_star DOUBLE NULL,
  h DOUBLE NULL,
  s DOUBLE NULL,
  v DOUBLE NULL,
  class_label VARCHAR(128) NULL,
  delta_e DOUBLE NULL,
  conditions_json TEXT NULL,
  allergies_json TEXT NULL,
  features_json TEXT NULL,
  quiet TINYINT(1) NOT NULL DEFAULT 1,
  INDEX idx_calib_samp_user_mod (user_id, modality, captured_at),
  INDEX idx_calib_samp_mod_time (modality, captured_at),
  INDEX idx_calib_samp_device (device_key, modality)
);

CREATE TABLE IF NOT EXISTS color_calib_state (
  state_key VARCHAR(128) PRIMARY KEY,
  scope VARCHAR(32) NOT NULL,
  modality VARCHAR(16) NOT NULL,
  tag VARCHAR(128) NULL,
  n INT NOT NULL DEFAULT 0,
  ewma_cct DOUBLE NULL,
  ewma_brightness DOUBLE NULL,
  ewma_L DOUBLE NULL,
  ewma_a DOUBLE NULL,
  ewma_b DOUBLE NULL,
  cct_bias_k DOUBLE NOT NULL DEFAULT 0,
  brightness_bias DOUBLE NOT NULL DEFAULT 0,
  thresh_delta_e_adj DOUBLE NOT NULL DEFAULT 0,
  thresh_a_heat_adj DOUBLE NOT NULL DEFAULT 0,
  thresh_b_yellow_adj DOUBLE NOT NULL DEFAULT 0,
  state_json TEXT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_calib_state_scope_mod (scope, modality),
  INDEX idx_calib_state_tag (tag)
);

CREATE TABLE IF NOT EXISTS affiliate_links (
  id INT AUTO_INCREMENT PRIMARY KEY,
  slug VARCHAR(100) NOT NULL UNIQUE COMMENT '短網址代稱，例如 olive-oil-01',
  title VARCHAR(255) NOT NULL COMMENT '商品或餐廳名稱',
  platform_name VARCHAR(50) NOT NULL COMMENT '主要平台，如 iHerb / Amazon / Klook',
  button_text VARCHAR(100) DEFAULT '前往查看優惠' COMMENT '按鈕顯示文字',
  url_tw TEXT NULL COMMENT '台灣訪客專屬網址',
  url_us TEXT NULL COMMENT '美國/英語系訪客網址',
  url_jp TEXT NULL COMMENT '日本訪客網址',
  url_default TEXT NOT NULL COMMENT '預設全球通用網址 (必填防呆)',
  is_active TINYINT(1) DEFAULT 1 COMMENT '1=啟用, 0=停用',
  click_count INT DEFAULT 0 COMMENT '點擊次數統計',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO affiliate_links (slug, title, platform_name, button_text, url_tw, url_us, url_default)
VALUES (
  'test-olive-oil',
  '冷壓初榨橄欖油',
  'iHerb / Amazon',
  '購買推薦健康好油',
  'https://iherb.com',
  'https://amazon.com',
  'https://iherb.com'
)
ON DUPLICATE KEY UPDATE
  title=VALUES(title),
  platform_name=VALUES(platform_name),
  button_text=VALUES(button_text),
  url_tw=VALUES(url_tw),
  url_us=VALUES(url_us),
  url_default=VALUES(url_default),
  is_active=1;
