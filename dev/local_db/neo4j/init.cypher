// ============================================================
// Mind-Log AI — Neo4j 스키마 초기화 (개발용)
// 소스: docs/architecture/DATA_SCHEMA.md 섹션 4
// ============================================================

// ===== Uniqueness Constraints (5개 노드 타입) =====

CREATE CONSTRAINT user_id_unique IF NOT EXISTS
  FOR (u:User) REQUIRE u.user_id IS UNIQUE;

CREATE CONSTRAINT session_id_unique IF NOT EXISTS
  FOR (s:Session) REQUIRE s.session_id IS UNIQUE;

CREATE CONSTRAINT emotion_key_unique IF NOT EXISTS
  FOR (e:Emotion) REQUIRE e.emotion_key IS UNIQUE;

CREATE CONSTRAINT topic_name_unique IF NOT EXISTS
  FOR (t:Topic) REQUIRE t.topic_name IS UNIQUE;

CREATE CONSTRAINT got_node_id_unique IF NOT EXISTS
  FOR (g:GoTNode) REQUIRE g.got_node_id IS UNIQUE;

// ===== Lookup Indexes =====

CREATE INDEX user_mysql_id IF NOT EXISTS
  FOR (u:User) ON (u.mysql_id);

CREATE INDEX session_mode IF NOT EXISTS
  FOR (s:Session) ON (s.mode);

CREATE INDEX emotion_category IF NOT EXISTS
  FOR (e:Emotion) ON (e.category);

CREATE INDEX topic_domain IF NOT EXISTS
  FOR (t:Topic) ON (t.domain);

CREATE INDEX got_episode IF NOT EXISTS
  FOR (g:GoTNode) ON (g.episode_id);

CREATE INDEX got_node_type IF NOT EXISTS
  FOR (g:GoTNode) ON (g.node_type);
