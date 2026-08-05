-- 회차별 당첨 번호
-- CHECK 제약을 스키마 레벨에 두는 것은 의도적이다. 수집기가 깨졌을 때
-- 오염 데이터가 들어가면 이후 모든 분석이 조용히 틀린다. 가장 바깥에서 막는다.
CREATE TABLE IF NOT EXISTS draws (
    round        INTEGER PRIMARY KEY,
    draw_date    TEXT NOT NULL,          -- YYYY-MM-DD
    group_no     INTEGER NOT NULL,
    d1 INTEGER NOT NULL, d2 INTEGER NOT NULL, d3 INTEGER NOT NULL,
    d4 INTEGER NOT NULL, d5 INTEGER NOT NULL, d6 INTEGER NOT NULL,
    bonus        TEXT,
    collected_at TEXT NOT NULL,
    CHECK (group_no BETWEEN 1 AND 5),
    CHECK (d1 BETWEEN 0 AND 9), CHECK (d2 BETWEEN 0 AND 9),
    CHECK (d3 BETWEEN 0 AND 9), CHECK (d4 BETWEEN 0 AND 9),
    CHECK (d5 BETWEEN 0 AND 9), CHECK (d6 BETWEEN 0 AND 9)
);

-- 추천 이력 (F5 검증용)
CREATE TABLE IF NOT EXISTS recommendations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    target_round  INTEGER NOT NULL,
    strategy      TEXT NOT NULL,          -- 'random' | 'eliminate'
    mode          TEXT NOT NULL,          -- 'spread' | 'concentrate'
    group_no      INTEGER NOT NULL,
    numbers       TEXT NOT NULL,
    rules_hash    TEXT,
    created_at    TEXT NOT NULL,
    CHECK (group_no BETWEEN 1 AND 5)
);

CREATE INDEX IF NOT EXISTS idx_rec_target ON recommendations(target_round);

-- 당첨 결과 대조
CREATE TABLE IF NOT EXISTS outcomes (
    recommendation_id INTEGER PRIMARY KEY REFERENCES recommendations(id),
    rank              INTEGER,            -- 1~7, NULL = 미당첨
    matched_tail      INTEGER NOT NULL,
    checked_at        TEXT NOT NULL
);
