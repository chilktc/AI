-- ============================================================
-- Mind-Log AI — MySQL 스키마 초기화 (개발용)
-- 소스: docs/architecture/DATA_SCHEMA.md + src/api/external_schemas.py
-- ============================================================

CREATE DATABASE IF NOT EXISTS mindlog
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE mindlog;

-- ------------------------------------------------------------
-- 2-1. users
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id          VARCHAR(64)   PRIMARY KEY,
    display_name     VARCHAR(50)   NULL,
    age_group        ENUM('10s','20s','30s','40s','50s','60s_plus') DEFAULT '30s',
    preferred_style  ENUM('warm','professional','casual','neutral') DEFAULT 'neutral',
    preferred_attitude ENUM('supportive','analytical','balanced','motivational') DEFAULT 'balanced',
    accessibility_needs JSON       DEFAULT (CAST('[]' AS JSON)),
    notification_enabled BOOLEAN   DEFAULT TRUE,
    total_sessions   INT           DEFAULT 0,
    total_episodes   INT           DEFAULT 0,
    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 2-2. sessions
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    session_id       VARCHAR(64)   PRIMARY KEY,
    user_id          VARCHAR(64)   NOT NULL,
    mode             ENUM('conversation','podcast') NOT NULL,
    status           ENUM('active','closed','expired') DEFAULT 'active',
    turn_count       INT           DEFAULT 0,
    episode_count    INT           DEFAULT 0,
    feedback_rating  INT           NULL,
    feedback_helpful BOOLEAN       NULL,
    feedback_comment VARCHAR(500)  NULL,
    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at        DATETIME      NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_sessions_user_created (user_id, created_at),
    INDEX idx_sessions_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 2-3. emotion_logs
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS emotion_logs (
    log_id              VARCHAR(64)   PRIMARY KEY,
    session_id          VARCHAR(64)   NOT NULL,
    user_id             VARCHAR(64)   NOT NULL,
    mode                ENUM('conversation','podcast') NOT NULL,
    turn_id             VARCHAR(64)   NULL,
    episode_id          VARCHAR(64)   NULL,
    primary_emotion     VARCHAR(100)  NOT NULL,
    intensity           FLOAT         NOT NULL,
    valence             FLOAT         NOT NULL,
    arousal             FLOAT         NOT NULL,
    secondary_emotions  JSON          DEFAULT (CAST('[]' AS JSON)),
    tone_recommendation VARCHAR(100)  NULL,
    trace_id            VARCHAR(64)   NULL,
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_emotion_user_created (user_id, created_at),
    INDEX idx_emotion_primary (primary_emotion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 2-4. podcast_episodes
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS podcast_episodes (
    episode_id          VARCHAR(64)   PRIMARY KEY,
    session_id          VARCHAR(64)   NOT NULL,
    user_id             VARCHAR(64)   NOT NULL,
    episode_title       VARCHAR(255)  NOT NULL,
    total_duration      FLOAT         NOT NULL,
    total_words         INT           DEFAULT 0,
    segment_count       INT           NOT NULL,
    key_insights        JSON          NOT NULL,
    themes              JSON          NOT NULL,
    reasoning_depth     ENUM('full','standard','minimal') DEFAULT 'standard',
    cover_image_url     VARCHAR(512)  NULL,
    intent_type         VARCHAR(100)  DEFAULT 'unknown',
    complexity_score    FLOAT         DEFAULT 0.0,
    safety_status       ENUM('safe','warning','crisis') DEFAULT 'safe',
    validation_score    FLOAT         DEFAULT 0.0,
    retry_count         INT           DEFAULT 0,
    pipeline_duration_ms INT          DEFAULT 0,
    script_text         TEXT          NULL
                                      COMMENT 'v3.0 평탄화된 전체 스크립트 텍스트',
    tts_markers_json    TEXT          NULL
                                      COMMENT 'v3.0 TTS 마커 JSON 배열',
    primary_emotion     VARCHAR(100)  DEFAULT 'neutral'
                                      COMMENT 'EmotionAgent primary_emotion',
    secondary_emotions  JSON          DEFAULT (CAST('[]' AS JSON))
                                      COMMENT 'secondary_emotions[0:2]',
    trace_id            VARCHAR(64)   NULL,
    correlation_id      VARCHAR(64)   NULL,
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_episode_user_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 2-6. learning_patterns
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS learning_patterns (
    pattern_id                  VARCHAR(64)   PRIMARY KEY,
    session_id                  VARCHAR(64)   NOT NULL,
    user_id                     VARCHAR(64)   NOT NULL,
    mode                        ENUM('conversation','podcast') NOT NULL,
    preferred_topics            JSON          DEFAULT (CAST('[]' AS JSON)),
    emotional_patterns          JSON          DEFAULT (CAST('[]' AS JSON)),
    interaction_style           VARCHAR(100)  DEFAULT 'standard',
    personalization_suggestions JSON          DEFAULT (CAST('[]' AS JSON)),
    effectiveness_score         FLOAT         DEFAULT 0.0,
    raw_learning_data           JSON          DEFAULT (CAST('{}' AS JSON)),
    trace_id                    VARCHAR(64)   NULL,
    created_at                  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_learning_user_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 2-7. visualization_meta
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS visualization_meta (
    visualization_id   VARCHAR(64)   PRIMARY KEY,
    session_id         VARCHAR(64)   NOT NULL,
    user_id            VARCHAR(64)   NOT NULL,
    mode               ENUM('conversation','podcast') NOT NULL,
    turn_id            VARCHAR(64)   NULL,
    episode_id         VARCHAR(64)   NULL,
    s3_key             VARCHAR(512)  NOT NULL,
    cdn_url            VARCHAR(512)  NOT NULL,
    image_prompt       TEXT          NOT NULL,
    interpretation_text TEXT         NOT NULL,
    trace_id           VARCHAR(64)   NULL,
    created_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
