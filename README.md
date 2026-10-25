# bh2-toolkit · 崩坏学园2 素材工具链与 QQ 机器人

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)
[![NoneBot2](https://img.shields.io/badge/NoneBot2-2.x-1f6feb.svg)](https://nonebot.dev/)
[![NapCat](https://img.shields.io/badge/NapCat-QQ%20gateway-2496ed.svg)](https://github.com/NapNeko/NapCatQQ)
[![Stars](https://img.shields.io/github/stars/yihejiekong/bh2-toolkit?style=social)](https://github.com/yihejiekong/bh2-toolkit/stargazers)
[![CI](https://github.com/yihejiekong/bh2-toolkit/actions/workflows/python.yml/badge.svg)](https://github.com/yihejiekong/bh2-toolkit/actions/workflows/python.yml)

群主没钱买红豆bot了，刚好自己有一台服务器，就自己动手做了。功能基本相似，从解包拿素材到制作成品各类装备卡都是用的游戏原生资源。

**0编程基础用户**：如果你完全看不懂这个项目，建议你安装一个模拟器，下好游戏并登录过一次，准备一个阿里云、腾讯云轻量级服务器。然后直接把这个项目的链接和服务器ip登录密码发给deepseek让他全程帮你配置完成就行。实测大概3块钱的token就能完成。

没有的功能：禁言、随机二刺螈图、up查询、嘴香嘴臭、阵营战分数（后面开了的话可能会加）、点歌

新增的功能：抽老婆、cg与立绘查询、官网公告推送、灵依娘哔哩哔哩动态推送、僵尸娘查询、自机角色查询、崩坏2表情包、玩家履历展示、群龙王、精英技能查询等

把「解包 → 素材 → 卡面 → 机器人」这条链路完整跑通的一套脚本：
从客户端资源里取出配置表与美术资源，做成图鉴卡、技能卡、僵尸娘资料卡，
再挂到一个 NoneBot2 + NapCat 的 QQ 机器人上。

> 本项目**不包含**任何游戏原始资源、账号凭据或服务器信息，要抓取玩家卡信息的话自己建个小号挂服务器就行。
> 所有素材可以直接照操作说明去抓；
> `.gitignore` 已经把素材目录、数据库、抓包与凭据文件排除在外。

## 目录

```
docs/     文档：使用说明、解包、图鉴表、卡面制作、机器人部署、玩家名片协议
unpack/   解包与素材导出（APK / AssetBundle / TSV / 纹理 / 立绘 / 图集）
cards/    卡面生成（装备卡 / 服装卡 / 徽章卡 / 使魔卡 / 角色卡 / 技能卡 / 僵尸娘）
bot/      NoneBot2 插件与部署文件（tools/ 下是建库脚本）
```

> 这个仓库里就不放任何游戏美术资源与成图了，自己按照下面的说明去游戏抓素材然后脚本一键出图。

## 快速开始

```bash
git clone <this repo> && cd bh2-toolkit
pip install -r requirements.txt

# 1) 解包（需要自备 APK 或从设备拉取热更资源）
python unpack/apk_extract.py
python unpack/bundle_decrypt.py
python unpack/export_tables.py

# 2) 出卡（需要一张列名对齐的图鉴表，见 docs/02）
python cards/batch.py --ids 897
python cards/build_zombie.py 57

# 3) 起机器人
cd bot && cp .env.example .env && pip install -r requirements.txt
python bot.py
```

## 文档索引

| 文档 | 内容 |
|---|---|
| **[docs/使用说明.md](docs/使用说明.md)** | **功能清单 + 每个功能的命令与截图 + 从零搭建的完整步骤（建议先看这篇）** |
| [docs/01-解包与素材提取.md](docs/01-解包与素材提取.md) | APK → AssetBundle → GGZV2 → TSV / 纹理 / 立绘 / 表情 / 服装图集 |
| [docs/02-图鉴表构建.md](docs/02-图鉴表构建.md) | 图鉴表字段、数值换算（满级/满破）、文本清洗、已知的坑 |
| [docs/03-卡面与素材制作.md](docs/03-卡面与素材制作.md) | HTML+截图出图、模板差异、批量、精英技能与僵尸娘的合并动图 |
| [docs/04-QQ机器人部署.md](docs/04-QQ机器人部署.md) | NapCat + NoneBot2 + systemd + 守护脚本 + 插件命令表 |
| [docs/05-玩家名片协议.md](docs/05-玩家名片协议.md) | 帧格式、校验算法、命令表、抓包取参、载荷解析 |
| [docs/06-素材来源一览.md](docs/06-素材来源一览.md) | 每份素材到底是从哪来的（解包 / 官网 / 渲染 / 手工），角色卡与表情包的获取方式 |

## 主要特性

* **纯 Python 解包**：13.4+ 的资源包（AES-CBC + 16 字节尾的 GGZV2）直接挂进 UnityPy；
* **卡面统一模板**：属性块 / 技能条 / 觉醒块 / 词条行，四类装备共用一套 CSS；
* **批量引擎**：并发 headless 截图、按背景色裁底、逐张校验有没有被裁；
* **不刷屏的素材推送**：多技能内容永远只发「一张卡 + 一张合并动图」；
* **常驻协议会话**：玩家名片查询登录一次长期复用，带心跳与断线重连。

## 许可与声明

* 代码 MIT。游戏内容（名称、图标、立绘、文本）版权归 miHoYo 所有，
  仓库不附带任何游戏资源，请勿分发。
* 解包与协议研究仅用于学习与个人使用，请遵守游戏用户协议；
  使用脚本登录账号存在风控风险，后果自负。
* GGZV2 解密算法来自社区逆向整理（Modder4869 / StudioDev 等），
  本项目只做 Python 适配。

## 致谢

* [UnityPy](https://github.com/K0lb3/UnityPy) —— Unity 资源解析
* [NoneBot2](https://github.com/nonebot/nonebot2) / [NapCat](https://github.com/NapNeko/NapCatQQ) —— 机器人框架与 QQ 网关
* 崩坏学园2 官方数据站（`benghuai.com/data`）—— 精英技能、僵尸娘、官网 CG 的公开资料

## 参与贡献

欢迎提 Issue 与 PR：请先看 [CONTRIBUTING.md](CONTRIBUTING.md)。
不要提交游戏素材与账号凭据（.gitignore 已排除，PR 里带上会被关闭）。
