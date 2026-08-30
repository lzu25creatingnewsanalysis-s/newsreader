# newsreader · 微博舆情事件采集器

舆情监测项目 **第一阶段：数据采集 + 入库**（赵喆 / 许博宇 负责部分）。

输入一个舆情**事件关键词**，用 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 的微博搜索/评论接口抓取，清洗后写入本地 **SQLite**。本项目**只做采集与入库，不做分析**——因果链、观点、立场、主题、风险等级等是后续阶段的预留字段。

## 采集口径（为什么这样设计）

- **抄 BettaFish / MindSpider 的采集模型**：按关键词深爬 + 给每条数据盖"事件"标签，事件 = 边界实体（`events` 表），不靠"搜到什么算什么"。
- **不做转发链溯源**：微博真实传播多为"截图传图"，机器可读的 `retweeted_status` 链并不常见；逐条追根帖是过度设计。`reposts_count` 仅作**热度指标**保留，截图/因果的传播分析属于**入库后**的事。
- **尽量全、别漏大影响力帖**：开全文抓取 + 一级/二级评论，单帖评论数、每关键词帖子数可配（默认 150 帖 / 200 评论）。

## 环境依赖

- Python 3.9+（实测 3.13）
- 在**本仓库同级目录**克隆 MediaCrawler（本项目直接 import 它的登录/搜索/评论模块，不修改它）：
  ```bash
  # 目录结构：newsreader 与 MediaCrawler 是兄弟目录
  parent/
    ├── MediaCrawler/          # git clone https://github.com/NanmiCoder/MediaCrawler
    └── newsreader/            # 本仓库
  ```
  若放在别处，用环境变量 `MEDIACRAWLER_DIR=/绝对路径/MediaCrawler` 指定。
- 安装 MediaCrawler 的依赖并装浏览器：
  ```bash
  cd MediaCrawler && pip install -r requirements.txt && playwright install chromium
  ```
- 采集走 **CDP 模式**，自动检测本机 **Chrome 或 Edge**（无需单独装 Chrome）。

## 快速开始

先**扫码登录一次**（会弹出二维码窗口，用微博 App 扫；登录态自动保存，之后免登录）：
```bash
cd newsreader
python main.py --keywords "朱雀回收" --event "朱雀回收" --login qrcode
```

之后直接按关键词抓全量（可逗号喂多个同事件关键词把边界铺宽）：
```bash
python main.py --keywords "朱雀回收,朱雀重入轨,朱雀三号" --event "朱雀回收"
```

不想扫码就用 cookie 登录（`m.weibo.cn` 已登录的 Cookie 串）：
```bash
python main.py --keywords "事件关键词" --login cookie --cookie "SUB=...; SUBP=...; _T_WM=..."
```

离线自检（建表 + 写读，不联网、不开浏览器）：
```bash
python main.py --selftest
```

## 命令行参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--keywords` | 必填 | 事件关键词，多个用英文逗号分隔 |
| `--event` | 取第一个关键词 | 事件名（边界） |
| `--login` | `qrcode` | `qrcode` 扫码 / `cookie` |
| `--cookie` | 空 | `--login cookie` 时的 Cookie 串 |
| `--max-notes` | `150` | 每关键词最多帖子（每页 10） |
| `--max-comments` | `200` | 单帖最多评论 |
| `--max-concurrency` | `1` | 并发抓评论（1 最稳，减少 302 限流） |
| `--sleep` | `3` | 请求间隔秒（防风控） |
| `--search-type` | `default` | `default`/`real_time`/`popular`/`video` |
| `--headless` | 关 | 无头（扫码登录用不了） |
| `--db` | `data/weibo.db` | SQLite 路径 |
| `--selftest` | — | 只做离线自检 |

> **幂等**：按 `post_id` / `comment_id` 去重（upsert），中断后重跑只补漏、不重复。

## 数据库结构（SQLite）

**events** — 事件边界实体
| 列 | 说明 |
|---|---|
| `id` | 事件 id |
| `name` | 事件名（唯一） |
| `keywords` | 该事件的搜索词（逗号分隔） |
| `add_ts` / `last_modify_ts` | 时间戳 |

**posts** — 以帖子为一条
| 列 | 说明 |
|---|---|
| `post_id` | 微博 mid（唯一） |
| `event_id` | 归属事件 |
| `source_keyword` | 哪个关键词搜到的 |
| `content` | 正文（已去 HTML） |
| `publish_time` / `publish_datetime` | 发布时间（unix 秒 / 可读） |
| `liked_count` / `comments_count` / `reposts_count` | 点赞 / 评论数 / 转发数（热度指标） |
| `post_url` | 帖子链接 |
| `author_hash` / `author_nickname` | 作者（匿名哈希 / 脱敏昵称） |
| `causal_chain` `opinion` `stance` `theme` `topic` `risk_level` | **预留**，采集阶段留空，供后续分析 |

**comments** — 每个帖子尽量多的评论/子评论
| 列 | 说明 |
|---|---|
| `comment_id` | 评论 id（唯一） |
| `post_id` | 所属帖子 |
| `content` / `publish_time` / `publish_datetime` | 评论内容与时间 |
| `like_count` / `reply_count` / `parent_comment_id` | 点赞 / 子回复数 / 父评论 id |
| `author_hash` / `author_nickname` | 评论者（匿名/脱敏） |
| `stance` `opinion` `topic` | **预留**，采集阶段留空 |

用任意 SQLite 工具打开 `data/weibo.db` 即可查询。

## 文件

```
newsreader/
├── main.py            # 入口：配参数 → 嫁接 MediaCrawler 存储 → 跑微博搜索/评论
├── store_adapter.py   # 把 MediaCrawler 的 note/comment 映射进本项目的表（不改 MediaCrawler）
├── db.py              # SQLite 建表 + upsert + 离线自检
├── README.md
└── .gitignore
```

## 参考项目

- [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) — 采集底座（登录/搜索/评论）。
- [BettaFish](https://github.com/666ghj/BettaFish) / [MindSpider](https://github.com/666ghj/MindSpider) — 事件-关键词扩面、话题关联的采集范式参考。

## 免责声明

本项目**仅供学习、学术研究与教育目的**使用。使用者须遵守各平台的服务条款与 `robots.txt`，合理控制请求频率，不得用于商业用途、大规模爬取或任何非法行为。相关责任由使用者自行承担。
