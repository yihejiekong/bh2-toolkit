# cards · 卡面生成

## 公共模块

| 文件 | 作用 |
|---|---|
| `paths.py` | 所有路径配置（`TABLES` / `MATERIALS` / `BUILD` / `BROWSER` / `FONT_BD`） |
| `bh2data.py` | 配置表读取（`read_tsv`）与 textmap 加载 |
| `cardgen.py` | 武器卡模板 + 通用工具（`clean` / `expand_params` / 图标与立绘解析） |

## 各卡种

| 脚本 | 卡种 | 批量脚本 |
|---|---|---|
| `cardgen.py` | 武器 | `batch.py` |
| `costume.py` | 服装 | `batch_fz.py` |
| `badge.py` | 徽章（被动技能装备） | `batch_badge.py` |
| `pet.py` | 使魔 | `batch_pet.py` |
| `build_chara_cards.py` | 角色 | 自带批量 |
| `build_skill_card.py` | 精英技能单卡 + 演示 | `batch_skill_cards.py` |
| `build_zombie.py` | 僵尸娘资料卡 + 合并演示动图 | `batch_zombie.py` |

## 汇总图

| 脚本 | 产出 |
|---|---|
| `build_elite_sheet.py` | 58 项精英技能 6 列网格 |
| `build_zombie_sheet.py` | 58 只僵尸娘 8 列网格 |

## 直接用

```bash
# 单张
python batch.py --ids 897          # 武器：内部ID 897
python batch_fz.py --ids 1001      # 服装
python batch_pet.py --ids 7016     # 使魔

# 全量
python batch.py                    # 武器（同名去重，只出最高星级）
python _verify_batch.py            # 检查是否有卡被裁掉

# 官网数据的两套（不依赖解包）
python build_skill_card.py --fetch && python build_elite_sheet.py
python build_zombie.py 57 && python build_zombie_sheet.py
```

> `--ids` 接受逗号分隔的「内部ID」。素材（图标/立绘/差分）缺失时脚本会打印
> `missing assets`，不会静默出一张缺图的卡。

## 出图流程

```
读 xlsx → 组数据 dict → 套 HTML 模板 → 写 build/<name>.html
        → headless 浏览器 2x 截图 → 按背景色裁底 → materials/**/PNG/
```

浏览器默认走 `P.BROWSER`（先找 Edge，再找 Chrome/Chromium），
可以用环境变量 `BH2_BROWSER` 指定。

详细说明见 [../docs/03-卡面与素材制作.md](../docs/03-卡面与素材制作.md)。
