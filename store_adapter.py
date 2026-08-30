# -*- coding: utf-8 -*-
"""Bridge MediaCrawler's weibo pipeline into our SQLite schema.

MediaCrawler's WeiboCrawler calls store.weibo.update_weibo_note(note_item) and
store.weibo.update_weibo_note_comment(note_id, comment_item) for every post &
comment (search / detail / comment pagination). Both are module-level functions
resolved at call time, so we swap them for ours -> no edits to MediaCrawler.

Each post is tagged with the current event id (set by main) + the keyword that
found it. The reserved analysis columns are deliberately NOT written.
"""
import re

import store.weibo as _weibo_store
from var import source_keyword_var
from tools import utils
from tools.user_hash import anonymize_user_id, mask_nickname

import db

EVENT_ID = None   # set by main() before crawling: which event this run collects


def _clean(html) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def _user_hash(uid) -> str:
    return anonymize_user_id(uid) if uid else None


def _when(created_at):
    if not created_at:
        return 0, ""
    return (
        utils.rfc2822_to_timestamp(created_at),
        str(utils.rfc2822_to_china_datetime(created_at)),
    )


def make_post(note_item) -> dict:
    """Bundle a search/detail card ({"mblog": {...}}) into one post row dict."""
    m = note_item.get("mblog") or {}
    user = m.get("user") or {}
    ts, dt = _when(m.get("created_at"))
    return dict(
        post_id=m.get("id"),
        event_id=EVENT_ID,
        source_keyword=source_keyword_var.get() or "",
        content=_clean(m.get("text")),
        publish_time=ts,
        publish_datetime=dt,
        liked_count=int(m.get("attitudes_count", 0) or 0),
        comments_count=int(m.get("comments_count", 0) or 0),
        reposts_count=int(m.get("reposts_count", 0) or 0),
        post_url=f"https://m.weibo.cn/detail/{m.get('id')}",
        author_hash=_user_hash(user.get("id")),
        author_nickname=mask_nickname(user.get("screen_name", "")),
    )


def make_comment(note_id, comment_item) -> dict:
    """Bundle one comment (hotflow item or sub-comment) into a comment row dict."""
    user = comment_item.get("user") or {}
    ts, dt = _when(comment_item.get("created_at"))
    return dict(
        comment_id=str(comment_item.get("id")),
        post_id=note_id,
        content=_clean(comment_item.get("text")),
        publish_time=ts,
        publish_datetime=dt,
        like_count=int(comment_item.get("like_count", 0) or 0),
        reply_count=int(comment_item.get("total_number", 0) or 0),
        parent_comment_id=str(comment_item.get("rootid", "") or ""),
        author_hash=_user_hash(user.get("id")),
        author_nickname=mask_nickname(user.get("screen_name", "")),
    )


async def update_weibo_note(note_item) -> None:
    """Override for store.weibo.update_weibo_note."""
    if not note_item:
        return
    post = make_post(note_item)
    if post.get("post_id"):
        db.upsert_post(post)
        utils.logger.info(f"[collector.store] post {post['post_id']} saved")


async def update_weibo_note_comment(note_id, comment_item) -> None:
    """Override for store.weibo.update_weibo_note_comment."""
    if not note_id or not comment_item:
        return
    comment = make_comment(note_id, comment_item)
    if comment.get("comment_id"):
        db.upsert_comment(comment)


def install() -> None:
    """Swap MediaCrawler's weibo store functions for ours (each run)."""
    _weibo_store.update_weibo_note = update_weibo_note
    _weibo_store.update_weibo_note_comment = update_weibo_note_comment
