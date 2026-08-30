# -*- coding: utf-8 -*-
"""Phase-1 storage: SQLite. Bets on BettaFish/MindSpider's collection model.

  * events   -> one row per monitored event (the boundary entity, tagged onto posts)
  * posts    -> one row per weibo post: time, interaction counts, url, anonymized
                author, which event/keyword found it, and *reserved* analysis
                columns (causal_chain/opinion/stance/theme/topic/risk_level) that
                are intentionally left NULL for the post-ingest analysis phase
                (causality / screenshot-propagation etc. live there, not here).
  * comments -> every comment/sub-comment fetched, linked to post_id.

No repost-chain tracing: real propagation is mostly screenshots (not machine
readable), so following retweeted_status is dropped as over-engineering;
reposts_count is kept only as a plain popularity metric.

Plain sqlite3 stdlib: zero extra deps. Single connection is safe (crawler is
single-threaded asyncio and each upsert is atomic).
"""
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL UNIQUE,        -- 事件名
    keywords       TEXT,                         -- 该事件的搜索词(逗号分隔)
    add_ts         INTEGER,
    last_modify_ts INTEGER
);

CREATE TABLE IF NOT EXISTS posts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id           TEXT NOT NULL UNIQUE,
    event_id          INTEGER,                   -- 需求: 事件边界(归属哪个事件)
    source_keyword    TEXT,                      -- 哪个关键词把它搜出来的
    content           TEXT,
    publish_time      INTEGER,                   -- 需求1: 时间 (unix 秒)
    publish_datetime  TEXT,
    liked_count       INTEGER,
    comments_count    INTEGER,
    reposts_count     INTEGER,                   -- 仅作热度指标,不做转发链
    post_url          TEXT,
    author_hash       TEXT,
    author_nickname   TEXT,
    -- 需求4: 预留(不填写)，供后续因果链/观点/立场/主题/风险分析
    causal_chain      TEXT,
    opinion           TEXT,
    stance            TEXT,
    theme             TEXT,
    topic             TEXT,
    risk_level        TEXT,
    add_ts            INTEGER,
    last_modify_ts    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_posts_publish_time ON posts(publish_time);
CREATE INDEX IF NOT EXISTS idx_posts_event        ON posts(event_id);
CREATE INDEX IF NOT EXISTS idx_posts_keyword      ON posts(source_keyword);

CREATE TABLE IF NOT EXISTS comments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_id        TEXT NOT NULL UNIQUE,
    post_id           TEXT,
    content           TEXT,
    publish_time      INTEGER,                   -- 评论时间
    publish_datetime  TEXT,
    like_count        INTEGER,
    reply_count       INTEGER,
    parent_comment_id TEXT,
    author_hash       TEXT,
    author_nickname   TEXT,
    -- 预留(不填写)：后续观点/立场/主题分析
    stance            TEXT,
    opinion           TEXT,
    topic             TEXT,
    add_ts            INTEGER,
    last_modify_ts    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_time ON comments(publish_time);
"""

_POST_COLS = (
    "post_id", "event_id", "source_keyword", "content", "publish_time",
    "publish_datetime", "liked_count", "comments_count", "reposts_count",
    "post_url", "author_hash", "author_nickname",
)
_COMMENT_COLS = (
    "comment_id", "post_id", "content", "publish_time", "publish_datetime",
    "like_count", "reply_count", "parent_comment_id", "author_hash",
    "author_nickname",
)

_conn = None
_path = None


def _ts() -> int:
    return int(time.time())


def init(db_path) -> None:
    """Open (or create + migrate) the sqlite database."""
    global _conn, _path
    _path = Path(db_path)
    _path.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(_path))
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA synchronous=NORMAL")
    _conn.executescript(_SCHEMA)
    _conn.commit()


def _connection() -> sqlite3.Connection:
    if _conn is None or _path is None:
        raise RuntimeError("db.init() must be called first")
    return _conn


def ensure_event(name: str, keywords=None) -> int:
    """Find or create an event row; return its id. The event = the boundary."""
    conn = _connection()
    kw = ",".join(keywords) if keywords else name
    row = conn.execute("SELECT id FROM events WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO events(name, keywords, add_ts, last_modify_ts) VALUES(?,?,?,?)",
        (name, kw, _ts(), _ts()),
    )
    conn.commit()
    return cur.lastrowid


def _upsert(table: str, key_col: str, cols, item) -> None:
    conn = _connection()
    now = _ts()
    data = {c: item.get(c) for c in cols}
    data["add_ts"] = now            # first-seen timestamp
    data["last_modify_ts"] = now    # refresh each time
    keys = list(cols) + ["add_ts", "last_modify_ts"]
    placeholders = ",".join("?" * len(keys))
    # only overwrite columns the caller actually provided (None = keep old value),
    # so a partial update never clobbers previously-known/reserved fields to NULL.
    update_cols = [c for c in keys if c not in (key_col, "add_ts") and data[c] is not None]
    updates = ",".join(f"{c}=excluded.{c}" for c in update_cols)
    sql = (
        f"INSERT INTO {table}({','.join(keys)}) VALUES({placeholders}) "
        f"ON CONFLICT({key_col}) DO UPDATE SET {updates}"
    )
    conn.execute(sql, [data[k] for k in keys])
    conn.commit()


def upsert_post(post) -> None:
    """Insert or update one post row (reserved analysis columns untouched)."""
    if not post or not post.get("post_id"):
        return
    _upsert("posts", "post_id", _POST_COLS, post)


def upsert_comment(comment) -> None:
    if not comment or not comment.get("comment_id"):
        return
    _upsert("comments", "comment_id", _COMMENT_COLS, comment)


def stats() -> dict:
    """Row counts for a run summary."""
    conn = _connection()
    return {
        "events": conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "posts": conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
        "comments": conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0],
        "db": str(_path),
    }


def self_test(db_path) -> None:
    """Offline check of schema + upsert round-trip (no network/browser)."""
    init(db_path)
    eid = ensure_event("测试事件", ["朱雀回收", "朱雀重入轨"])
    ensure_event("测试事件", ["ignored"])          # idempotent: must reuse id
    upsert_post({
        "post_id": "TEST001", "event_id": eid, "source_keyword": "朱雀回收",
        "content": "帖子正文", "publish_time": 1700000000,
        "publish_datetime": "2023-11-15 00:00:00",
        "liked_count": 10, "comments_count": 2, "reposts_count": 3,
        "post_url": "https://m.weibo.cn/detail/TEST001",
        "author_hash": "h1", "author_nickname": "作者",
    })
    upsert_post({"post_id": "TEST001", "content": "帖子正文(已更新)", "liked_count": 99})
    upsert_comment({
        "comment_id": "C1", "post_id": "TEST001", "content": "评论A",
        "publish_time": 1700000100, "publish_datetime": "2023-11-15 00:01:00",
        "like_count": 1, "reply_count": 0, "parent_comment_id": "",
        "author_hash": "u1", "author_nickname": "网友",
    })
    conn = _connection()
    post = conn.execute("SELECT * FROM posts WHERE post_id='TEST001'").fetchone()
    events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    comment = conn.execute("SELECT * FROM comments WHERE comment_id='C1'").fetchone()
    reserved = [post[k] for k in ("causal_chain", "opinion", "stance", "theme", "topic", "risk_level")]
    assert events == 1, "ensure_event must be idempotent"
    assert post["event_id"] == eid, "post tagged with event"
    assert post["liked_count"] == 99, "upsert should refresh post"
    assert post["source_keyword"] == "朱雀回收", "source_keyword preserved on partial update"
    assert comment["post_id"] == "TEST001", "comment link"
    assert all(v is None for v in reserved), "reserved columns must stay empty for now"
    conn.executescript("DROP TABLE posts; DROP TABLE comments; DROP TABLE events;")
    conn.commit()
    print("[self_test] ok -> event tagging + post/comment round-trip + reserved empty")
