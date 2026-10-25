# bot · NoneBot2 插件与部署

```
bot.py                 入口（注册 OneBot v11 适配器，加载插件）
pyproject.toml         nonebot 配置（插件目录 src/plugins）
requirements.txt       nonebot2 / onebot v11 / apscheduler / httpx / pillow
.env.example           环境变量样例（复制成 .env）
src/plugins/           13 个功能插件 + 若干公共模块
tools/import_db.py     建库：图鉴表 → bh2.db（equip / illust / illust_equip）
deploy/                systemd 单元与 NapCat 守护脚本
```

## 插件一览

| 插件 | 命令 | 依赖素材 |
|---|---|---|
| `equip_query` | `装备查询 <名称/ID>` | `材料/装备卡`、`图标`、`觉醒立绘` |
| `illust_query` | `立绘查询`、`CG`、`壁纸` | `觉醒立绘`、`官网CG` |
| `chara_query` | `查询角色`、`角色语音 <名>` | `角色卡` |
| `guess_game` | `猜装备`、`猜装备排行榜` | `图标` + `bh2.db` |
| `wife` | `抽老婆`、`换老婆` | `角色卡`/`立绘` |
| `emote` | `表情包` | `精选表情图` |
| `announce` | `开启公告` / `关闭公告` | —（B 站 API） |
| `official_news` | `开启官网公告` / `关闭官网公告` | —（官网 API） |
| `auto_reply` | `新增回复` 等 5 条 | —（`bh2.db`） |
| `module_switch` | `开启功能` / `关闭功能` / `功能列表` | —（`bh2.db`） |
| `elite_skill` | `精英技能`、`查询技能 <名/编号>` | `精英技能/` |
| `zombie` | `僵尸娘`、`查询怪物 <名/NO.xx>` | `僵尸娘/` |
| `dragon` | `群龙王` | —（`bh2.db`） |
| `player_query` | `查询玩家 <uid>`、`查询b2玩家/查询官服玩家`、`绑定玩家`、`查询自己`、`查询@某人` | 需 `bh2-query` 服务 |

公共模块：`_config`（路径/管理员）、`_media`（发本地图片）、`_session`（多轮会话）、
`_dragon_card`（龙王榜渲染）、`player/`（协议、解析、渲染、常驻服务）。

## 启动

```bash
pip install -r requirements.txt
cp .env.example .env      # 填 ACCESS_TOKEN / BOT_ADMINS / MATERIAL_ROOT

python tools/import_db.py # 建库（装备查询/猜装备/立绘查询依赖它）
python bot.py
```

日志里每个插件都会打一行 `Succeeded to load plugin "...";`，
有 `Failed to load` 就是依赖或路径问题。

## 部署

```bash
sudo cp deploy/bh2-bot.service /etc/systemd/system/
sudo cp deploy/bh2-query.service /etc/systemd/system/   # 只有用玩家名片才需要
sudo systemctl daemon-reload
sudo systemctl enable --now bh2-bot
```

NapCat 守护见 `deploy/napcat-guard.sh` + `napcat-guard.service`。

完整步骤（含 NapCat Docker、字体、素材同步）见
[../docs/04-QQ机器人部署.md](../docs/04-QQ机器人部署.md)，
功能清单与逐步搭建见 [../docs/使用说明.md](../docs/使用说明.md)，
玩家名片的协议细节见 [../docs/05-玩家名片协议.md](../docs/05-玩家名片协议.md)。

## 注意

* `.env`、`servers.json`、`bh2.db` 都含敏感信息，已在 `.gitignore` 里，别提交；
* 同一个 QQ 只能在一个地方在线，本地调试前先停掉云端 NapCat；
* 管理员（可改固定回复、开关功能、不限抽卡次数）由 `.env` 的 `BOT_ADMINS` 指定。
