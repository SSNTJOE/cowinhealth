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
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS health_records (
  record_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(32) NOT NULL,
  record_date DATETIME NOT NULL,
  symptoms TEXT NULL,
  discomfort TEXT NULL,
  face_color VARCHAR(64) NULL,
  lip_color VARCHAR(64) NULL,
  tongue_body_color VARCHAR(64) NULL,
  tongue_coat_color VARCHAR(64) NULL,
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
  diet_advice VARCHAR(80) NULL,
  diet_url TEXT NULL,
  acupoint_url TEXT NULL,
  pulse_json TEXT NULL,
  face_grid_json TEXT NULL,
  complexion_label VARCHAR(64) NULL,
  complexion_hex VARCHAR(16) NULL,
  CONSTRAINT fk_health_user FOREIGN KEY (user_id) REFERENCES users(user_id)
);
