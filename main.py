# -*- coding: utf-8 -*-
"""Phase-1 weibo event collector (赵喆 / 许博宇 部分).

输入事件关键词 -> 用 MediaCrawler 的微博搜索/评论接口抓取，写入本地 SQLite：
  events    一个事件一条(事件边界实体)
  posts     以帖子为一条(时间/点赞/评论数/转发数/所属事件/来源关键词/预留分析字段)
  comments  每个帖子尽量多的评论/子评论(时间/点赞/回复/预留字段)

采集口径抄 BettaFish/MindSpider：按关键词深爬 + 给每条盖事件标签；不做转发链溯源
(真实传播多为截图，入库后再说，见预留字段)。

依赖：同目录 ../MediaCrawler (已 clone)。用 CDP 模式自动检测 Edge/Chrome，
首次运行会弹出浏览器扫码登录(微博)，登录态自动保存，之后复用。

用法：
  python main.py --keywords "关键词[,关键词2...]" --event "事件名"   # 抓取并入库
  python main.py --keywords "关键词" --login cookie --cookie "<cookie串>"
  python main.py --selftest                               # 离线自检(建表+写读)
"""
import argparse
import asyncio
import io
import os
import sys
from pathlib import Path

# 强制 UTF-8 以免 Windows 控制台输出中文报错
if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
# MediaCrawler 作为子目录内置；也可用环境变量 MEDIACRAWLER_DIR 指定别处的绝对路径
MEDIA = Path(os.environ.get("MEDIACRAWLER_DIR") or (ROOT / "MediaCrawler"))
DB_PATH = str(ROOT / "data" / "weibo.db")

# 抓取口径：目标=事件链路，尽量全、别漏大影响力帖子
DEFAULTS = dict(
    keywords="",
    max_notes=150,            # 每个关键词最多帖子(每页10条) -> 页数=附近值
    max_comments_per_post=200,  # 单帖最多评论(热评+分页，尽可能多)
    max_concurrency=1,        # 并发抓评论数(1 最稳，能显著减少评论接口 302 抢限)
    sleep_sec=3,              # 频率控制/防风控
    headless=False,           # 首次扫码需开浏览器
    login_type="qrcode",      # qrcode | cookie
    cookies="",
    search_type="default",    # default|real_time|popular|video
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="微博舆情事件关键词采集(入库)")
    p.add_argument("--keywords", default=DEFAULTS["keywords"], help="事件关键词，多个用英文逗号分隔")
    p.add_argument("--event", default="", help="事件名(边界)；留空则用第一个关键词当事件名")
    p.add_argument("--db", default=DB_PATH, help="sqlite 数据库路径")
    p.add_argument("--max-notes", type=int, default=DEFAULTS["max_notes"], help="每关键词最多帖子")
    p.add_argument("--max-comments", type=int, default=DEFAULTS["max_comments_per_post"], help="单帖最多评论")
    p.add_argument("--max-concurrency", type=int, default=DEFAULTS["max_concurrency"])
    p.add_argument("--sleep", type=float, default=DEFAULTS["sleep_sec"], help="每次请求间隔秒")
    p.add_argument("--login", choices=["qrcode", "cookie"], default=DEFAULTS["login_type"])
    p.add_argument("--cookie", default=DEFAULTS["cookies"], help="--login cookie 时的 cookie 串")
    p.add_argument("--search-type", default=DEFAULTS["search_type"])
    p.add_argument("--headless", action="store_true", help="无头模式(不弹窗，登录用不了)")
    p.add_argument("--selftest", action="store_true", help="只做离线自检，不爬取")
    return p.parse_args()


def _set_mediacrawler_config(args: argparse.Namespace) -> None:
    """把我们的参数灌进 MediaCrawler 的 config 模块(运行前必须执行)。"""
    import config
    config.PLATFORM = "wb"
    config.CRAWLER_TYPE = "search"
    config.KEYWORDS = args.keywords
    config.LOGIN_TYPE = args.login
    config.COOKIES = args.cookie
    config.HEADLESS = args.headless
    config.MAX_CONCURRENCY_NUM = args.max_concurrency
    config.CRAWLER_MAX_SLEEP_SEC = args.sleep
    config.START_PAGE = 1
    config.CRAWLER_MAX_NOTES_COUNT = args.max_notes
    config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = args.max_comments
    # 完备性：帖子全文 + 一级/二级评论都抓，不抓图片(本阶段无关)
    config.ENABLE_WEIBO_FULL_TEXT = True
    config.ENABLE_GET_COMMENTS = True
    config.ENABLE_GET_SUB_COMMENTS = True
    config.ENABLE_GET_MEIDAS = False
    config.ENABLE_GET_WORDCLOUD = False
    config.WEIBO_SEARCH_TYPE = args.search_type
    # 用 CDP 模式(自动检测 Edge/Chrome)：MediaCrawler 标准模式写死 channel="chrome"，
    # 本机无 Chrome 但有 Edge；CDP 模式走真实浏览器，反检测更好。
    config.ENABLE_CDP_MODE = True
    config.CDP_CONNECT_EXISTING = False      # 自动启动一个检测到的浏览器（而非连已有）
    config.CDP_HEADLESS = args.headless
    config.CUSTOM_BROWSER_PATH = ""          # 留空=自动检测 Chrome/Edge
    config.SAVE_LOGIN_STATE = True           # 登录态存到 MediaCrawler/browser_data/，下次复用
    config.USER_DATA_DIR = "%s_user_data_dir"
    config.SAVE_DATA_OPTION = "sqlite"       # 我们不写 MediaCrawler 自己的表
    config.SAVE_DATA_PATH = ""
    return config


async def _run_crawler() -> None:
    from media_platform.weibo import WeiboCrawler
    crawler = WeiboCrawler()
    try:
        await crawler.start()
    finally:
        await crawler.close()


def main() -> None:
    args = parse_args()

    import db
    if args.selftest:
        db.self_test(DB_PATH)
        return

    os.chdir(MEDIA)                      # libs/stealth.min.js 等相对资源
    sys.path.insert(0, str(MEDIA))

    _set_mediacrawler_config(args)

    db.init(args.db)
    import store_adapter
    store_adapter.install()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    event_name = args.event or (keywords[0] if keywords else "")
    if not event_name:
        print("[collector] 需要 --keywords 指定事件关键词(或 --event 事件名)")
        return
    store_adapter.EVENT_ID = db.ensure_event(event_name, keywords)

    print(f"[collector] event = {event_name!r} (id={store_adapter.EVENT_ID})")
    print(f"[collector] DB = {args.db}")
    print(f"[collector] keywords = {args.keywords!r} | max_notes={args.max_notes} | "
          f"max_comments={args.max_comments} | login={args.login}")

    try:
        asyncio.run(_run_crawler())
    except KeyboardInterrupt:
        print("\n[collector] interrupted by user")
    finally:
        print(f"[collector] summary: {db.stats()}")


if __name__ == "__main__":
    main()
