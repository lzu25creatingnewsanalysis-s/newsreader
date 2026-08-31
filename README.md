## 使用
克隆仓库到本地
```bash
git clone https://github.com/yellowbutton/newsreader.git
```
依赖 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)
```bash
git clone https://github.com/NanmiCoder/MediaCrawler MediaCrawler
cd MediaCrawler && pip install -r requirements.txt && playwright install
```
回到newsreader文件夹
```bash
cd ..
```
采集会自动使用本机的 Chrome 或 Edge。
首次扫码登录：
```bash
python main.py --keywords "朱雀回收" --event "朱雀回收" --login qrcode
```
之后不必登陆：
```bash
python main.py --keywords "朱雀回收,朱雀重入轨,朱雀三号" --event "朱雀回收"
```
cookie登录：
```bash
python main.py --keywords "关键词" --login cookie --cookie "SUB=...; SUBP=...; _T_WM=..."
```

常用参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--keywords` | 必填 | 事件关键词，多个用英文逗号分隔 |
| `--event` | 第一个关键词 | 事件名 |
| `--login` | `qrcode` | `qrcode` 扫码 / `cookie` |
| `--max-notes` | `150` | 每关键词最多帖子 |
| `--max-comments` | `200` | 单帖最多评论 |
| `--selftest` | — | 离线自检（不联网、不开浏览器） |

数据库在 `data/weibo.db`。

## 数据库结构

**events**

| 字段 | 说明 |
|---|---|
| `id` | 事件 id |
| `name` | 事件名 |
| `keywords` | 搜索词 |

**posts**

| 字段 | 说明 |
|---|---|
| `post_id` | 微博 id |
| `event_id` | 所属事件 |
| `source_keyword` | 关键词 |
| `content` | 正文 |
| `publish_time` / `publish_datetime` | 发布时间 |
| `liked_count` / `comments_count` / `reposts_count` | 点赞 / 评论数 / 转发数 |
| `post_url` | 链接 |
| `author_hash` / `author_nickname` | 作者 |
| `causal_chain` `opinion` `stance` `theme` `topic` `risk_level` | **预留** |

**comments**

| 字段 | 说明 |
|---|---|
| `comment_id` | 评论 id |
| `post_id` | 所属 |
| `content` | 评论内容 |
| `publish_time` / `publish_datetime` | 评论时间 |
| `like_count` / `reply_count` / `parent_comment_id` | 点赞 / 子回复数 / 父评论 id |
| `author_hash` / `author_nickname` | 评论者 |
| `stance` `opinion` `topic` | **预留** |
