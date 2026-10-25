# -*- coding: utf-8 -*-
"""崩坏学园2官网角色批量爬取 + 角色卡生成（本地化版）。

数据源：benghuai.com 首页角色板块（static-event.benghuai.com/.../chara/{id}/）
产出（角色卡统一归并到素材根 materials/角色卡/ 下）：
  materials/角色卡/{id}/assets/{role,role_cut,info,title}.png
  materials/角色卡/{id}/voice/{china|japan|yueyu}/00X.mp3   语音全部本地化
  materials/角色卡/{id}.html                                角色卡页面（无语音按钮）
  materials/角色卡/{id}_card.png                            截图成图（发QQ用）
  materials/角色卡/roles.json                               全角色档案（供bot查询用）

说明：
  - 偶数位角色（官网布局中立绘在文字左侧）的立绘做镜像，使角色面向左侧文字
  - 诗音(shion)的官网资源目录是 sion（官网自身不一致，这里做映射）
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image
import paths as P

ROOT = Path(__file__).parent
OUT = ROOT / "materials" / "角色卡"
STATIC = "https://static-event.benghuai.com/new_mihoyo_homepage/chara"
HOME = "https://www.benghuai.com/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 语音条数（官网每个语言目录 001~005）
VOICE_COUNT = 5

# 角色定义（按官网出现顺序排列，index 决定奇偶 → 是否镜像立绘）
# (id, 资源目录id, 中文名, 英文名, 简介文字)
ROLES = [
    ("kiana", "kiana", "琪亚娜·卡斯兰娜", "KIANA KASLANA",
     "卡斯兰娜家族第 69 世传人。在琪亚娜 12 岁那年，父亲携年幼的她只身来到极东之地，"
     "调查被视作疑似崩坏前兆事件的\u201c地铁沙林恐怖事件\u201d。琪亚娜 14 岁时，父亲将家学之奥义"
     "尽数传于她，随后消失在了众人的视线中，只留下一句——\u201c我去探寻崩坏的本源了\u201d。"),
    ("mei", "mei", "雷电芽衣", "RAIDEN MEI",
     "父亲原是某著名外资企业的社长，在芽衣 15 岁时，企业深受金融危机影响，父亲也深陷经济弊案，"
     "终至牢狱之灾，几乎全部家产都被冻结。这次事件对芽衣的世界影响重大，也使得她往日开朗的性格"
     "变得有点孤僻诡异。"),
    ("bronya", "bronya", "布洛妮娅·扎伊切克", "BRONYA ZAYCHIK",
     "俄罗斯重工业家族企业的养女，是该企业次世代人形作战兵器项目试验体。布洛妮娅在实验中被"
     "抹除人格特性以便与脑机接口更好的兼容，从而达到将人性与机械相融合的境界。"),
    ("himeko", "himeko", "无量塔姬子", "MURATA HIMEKO", ""),
    ("theresa", "theresa", "德丽莎·阿波卡利斯", "THERESA APOCALYPSE", ""),
    ("seele", "seele", "希儿·芙乐艾", "SEELE VOLLEREI", ""),
    ("sin", "sin", "杏·玛尔", "SIN MAL", ""),
    ("kyuusyou", "kyuusyou", "蓬莱寺九霄", "HOURAIJI KYUUSYOU", ""),
    ("yssring", "yssring", "伊瑟琳·利维休斯", "YSSRING LEAVTRUTH", ""),
    ("fuhua", "fuhua", "符华", "FU HUA", ""),
    ("kika", "kika", "无色辉火", "MUSHOKU KIKA", ""),
    ("sirin", "sirin", "西琳", "SIRIN", ""),
    ("rita", "rita", "丽塔", "RITA", ""),
    ("ninti", "ninti", "宁蒂", "NINTI", ""),
    ("jyahnar", "jyahnar", "迦娜", "JYAHNAR", ""),
    ("fran", "fran", "芙兰", "FRAN", ""),
    ("femirins", "femirins", "菲米莉丝", "FEMIRINS", ""),
    ("shion", "sion", "诗音", "SION", ""),
    ("karin", "karin", "卡琳·梅莉德", "KARIN MERED", ""),
    ("arkria", "arkria", "阿库莉亚·赫萝普特", "ARKRIA HROPTR", ""),
    ("kurenai", "kurenai", "红理惠", "KURENAI RIE", ""),
    ("laniaitte_gordius", "laniaitte_gordius", "拉妮艾特·戈尔迪乌斯", "LANIAITTE·GORDIUS", ""),
    ("bronya_zaychik", "bronya_zaychik", "布洛妮娅【银狼归来】", "BRONYA ZAYCHIK", ""),
    ("huang_lan", "huang_lan", "煌岚", "HUANG LAN", ""),
    ("tiara_starlumos", "tiara_starlumos", "蒂亚拉·星灯", "TIARA·STARLUMOS", ""),
    ("mushoku_kika", "mushoku_kika", "无色辉火【赤烬重燃】", "MUSHOKU KIKA", ""),
]

# 官网顺序索引（0 起）→ 偶数位(第2/4/6...位)立绘在文字左侧，卡里需镜像
MIRROR_IDS = {rid for i, (rid, _, _, _, _) in enumerate(ROLES) if i % 2 == 1}

# 立绘右移约10%卡片宽度的角色（超出部分由 overflow:hidden 裁掉）
SHIFT_RIGHT = {
    "arkria", "fran", "fuhua", "himeko", "huang_lan", "karin", "kiana",
    "kyuusyou", "laniaitte_gordius", "mei", "seele", "shion", "sin",
    "tiara_starlumos",
}
# 额外右移量（在10%基础上叠加，百分比相对卡片宽度）
SHIFT_EXTRA = {
    "arkria": 25,
    "shion": 20,
    "tiara_starlumos": 10,
}

# 档案数据（从官网 info.png 逐张人工读取录入）
PROFILES = {
    "kiana": {"cv_cn": "陶典", "cv_jp": "钉宫理惠", "birthday": "12月7日", "age": "16岁",
              "height": "163cm", "weight": "48kg", "measurements": "84-59-87cm"},
    "mei": {"cv_cn": "TetraCalyx", "cv_jp": "泽城美雪", "birthday": "4月13日", "age": "17岁",
            "height": "172cm", "weight": "50kg", "measurements": "89-62-90cm"},
    "bronya": {"cv_cn": "hanser", "cv_jp": "阿澄佳奈", "birthday": "8月18日", "age": "14岁",
               "height": "147cm", "weight": "40kg", "measurements": "74-55-76cm"},
    "himeko": {"cv_cn": "酒儿", "cv_jp": "田中理惠", "birthday": "6月11日", "age": "27岁",
               "height": "167cm", "weight": "55kg", "measurements": "95-61-92cm"},
    "theresa": {"cv_cn": "Sky花铃", "cv_jp": "田村由加莉", "birthday": "3月28日", "age": "？？？",
                "height": "145cm", "weight": "38kg", "measurements": "70-58-73cm"},
    "seele": {"cv_cn": "牛奶君", "cv_jp": "中原麻衣", "birthday": "10月18日", "age": "14岁",
              "height": "149cm", "weight": "42kg", "measurements": "74-56-78cm"},
    "sin": {"cv_cn": "小N", "cv_jp": "上坂堇", "birthday": "9月9日", "age": "14岁",
            "height": "148cm", "weight": "42kg", "measurements": "75-57-75cm"},
    "kyuusyou": {"cv_cn": "陶典", "cv_jp": "优木加奈", "birthday": "12月24日", "age": "16岁",
                 "height": "159cm", "weight": "47kg", "measurements": "86-56-88cm"},
    "yssring": {"cv_cn": "秦紫翼", "cv_jp": "井泽诗织", "birthday": "1月8日", "age": "16岁",
                "height": "151cm", "weight": "44kg", "measurements": "73-55-75cm"},
    "fuhua": {"cv_cn": "Mace", "cv_jp": "高山南", "birthday": "2月9日", "age": "未知",
              "height": "165cm", "weight": "53kg", "measurements": "84-64-90cm"},
    "kika": {"cv_cn": "宴宁", "cv_jp": "石川由依", "birthday": "5月2日", "age": "16岁",
             "height": "156cm", "weight": "46kg", "measurements": "82-54-84"},
    "sirin": {"cv_cn": "陈婷婷", "cv_jp": "丹下樱", "birthday": "6月23日", "age": "13岁",
              "height": "145cm", "weight": "40kg", "measurements": "73-54-77"},
    "rita": {"cv_cn": "小N", "cv_jp": "悠木碧", "birthday": "3月1日", "age": "20岁",
             "height": "168cm", "weight": "56kg", "measurements": "92-61-92"},
    "ninti": {"cv_cn": "宋媛媛", "cv_jp": "长绳麻理亚", "cv_gd": "闲踏梧桐",
              "birthday": "11月15日", "age": "13岁",
              "height": "145cm", "weight": "37kg", "measurements": "72-55-74"},
    "jyahnar": {"cv_cn": "金娜", "cv_jp": "能登麻美子", "birthday": "9月19日", "age": "未知",
                "height": "166cm", "weight": "47kg", "measurements": "87-63-91"},
    "fran": {"cv_cn": "小泪", "cv_jp": "内田真礼", "birthday": "7月26日", "age": "未知",
             "height": "153cm", "weight": "45kg", "measurements": "78-55-76"},
    "femirins": {"cv_cn": "多多poi", "cv_jp": "种崎敦美", "birthday": "7月6日", "age": "未知",
                 "height": "150cm（默认）", "weight": "190g", "measurements": "79-54-77（默认）"},
    "shion": {"cv_cn": "刘雯", "cv_jp": "日高里菜", "birthday": "4月21日", "age": "500岁以上",
              "height": "148cm", "weight": "45kg", "measurements": "75-55-77"},
    "karin": {"cv_cn": "陶典", "cv_jp": "小清水亚美", "birthday": "4月3日", "age": "16岁",
              "height": "169cm", "weight": "52kg", "measurements": "81-61-86"},
    "arkria": {"cv_cn": "张琦", "cv_jp": "土屋李央", "birthday": "6月24日", "age": "16岁",
               "height": "160cm", "weight": "49kg", "measurements": "80-55-83"},
    "kurenai": {"cv_cn": "葛子瑞", "cv_jp": "和气杏未", "birthday": "8月24日", "age": "10岁",
                "height": "139cm", "weight": "33kg", "measurements": "73-49-75"},
    "laniaitte_gordius": {"cv_cn": "赵爽", "cv_jp": "田所梓", "birthday": "9月23日", "age": "16岁",
                          "height": "165cm", "weight": "50kg", "measurements": "80-58-84"},
    "bronya_zaychik": {"cv_cn": "喵酱", "cv_jp": "阿澄佳奈", "birthday": "8月18日", "age": "？？？",
                       "height": "165cm", "weight": "50kg", "measurements": "79-60-83"},
    "huang_lan": {"cv_cn": "龟娘", "cv_jp": "相坂优歌", "birthday": "7月18日", "age": "16岁",
                  "height": "150cm", "weight": "44kg", "measurements": "80-58-84"},
    "tiara_starlumos": {"cv_cn": "王晓彤", "cv_jp": "矶部花凛", "birthday": "11月23日", "age": "14岁",
                        "height": "142cm", "weight": "39kg", "measurements": "73-57-69"},
    "mushoku_kika": {"cv_cn": "宴宁", "cv_jp": "石川由依", "birthday": "5月2日", "age": "？？？",
                     "height": "166cm", "weight": "64kg", "measurements": "83-65-90"},
}


def download(url, path: Path):
    if path.exists():
        return True
    try:
        req = urllib.request.Request(url, headers=UA)
        data = urllib.request.urlopen(req, timeout=20).read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return True
    except Exception as e:
        print(f"  [warn] 下载失败 {url}: {e}")
        return False


def download_voices(rid: str, res_id: str):
    """下载该角色全部语音到本地（china/japan；ninti 额外有 yueyu）。"""
    langs = ["china", "japan", "yueyu"] if rid == "ninti" else ["china", "japan"]
    ok = 0
    for lang in langs:
        for i in range(1, VOICE_COUNT + 1):
            f = OUT / rid / "voice" / lang / f"00{i}.mp3"
            if download(f"{STATIC}/{res_id}/{lang}/00{i}.mp3", f):
                ok += 1
    return ok


def make_role_png(rid: str, res_id: str, mirror: bool):
    """下载立绘原图；偶数位角色镜像（面向左侧文字）。不做透明边裁切。"""
    png = OUT / rid / "assets" / "role.png"
    if not download(f"{STATIC}/{res_id}/role.png", png):
        return False
    im = Image.open(png)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    if mirror:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    im.save(OUT / rid / "assets" / "role_final.png")
    return True


def make_title_fade(rid: str):
    """title.png 是上下两段（上原版/下淡色），裁下半段淡色做左上角水印。"""
    t = OUT / rid / "assets" / "title.png"
    if not t.exists():
        return
    im = Image.open(t).convert("RGBA")
    w, h = im.size
    im.crop((0, h // 2, w, h)).save(OUT / rid / "assets" / "title_fade.png")


HTML_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{cn} — 崩坏学园2 角色卡</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    background: #e9eef3;
    min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    padding: 40px 24px;
  }}
  .card {{
    width: 1240px; max-width: 100%;
    background: linear-gradient(180deg, #fbfdff 0%, #f2f6fa 100%);
    border: 1px solid #d5e2ef;
    border-radius: 20px;
    box-shadow: 0 16px 48px rgba(90,130,180,.22);
    position: relative;
    overflow: hidden;
  }}
  .banner {{
    height: 150px;
    margin: 18px 18px 0;
    border-radius: 14px;
    background:
      radial-gradient(circle at 85% 25%, rgba(255,255,255,.9) 0 55px, transparent 56px),
      radial-gradient(circle at 70% 80%, rgba(255,255,255,.6) 0 30px, transparent 31px),
      linear-gradient(100deg, #cfe4f7 0%, #e8f2fb 45%, #f6fafe 100%);
    border: 1px solid #d8e8f6;
    position: relative;
    display: flex; align-items: center;
  }}
  .banner .title-fade {{
    position: absolute; left: 24px; top: 12px;
    height: 120px; width: auto; opacity: .5; pointer-events: none;
  }}
  .banner .word {{
    position: absolute; right: 40px; top: 22px;
    font-size: 56px; font-weight: 800; letter-spacing: 12px;
    color: rgba(255,255,255,.92);
    text-shadow: 0 2px 0 #b9d6ef, 0 4px 12px rgba(140,180,220,.5);
  }}
  .banner .cn {{
    position: absolute; left: 30px; bottom: 16px;
    font-size: 14px; color: #6d93bd; letter-spacing: 2px;
  }}
  .body {{ display: flex; padding: 0 18px 18px; }}
  .info {{ flex: 1; padding: 30px 8px 10px 22px; color: #3a4a5c; position: relative; z-index: 2; }}
  .en-name {{ font-size: 28px; font-weight: 700; letter-spacing: 3px; color: #b9cede; }}
  .cn-name {{ font-size: 34px; font-weight: 800; color: #33526e; margin: 2px 0 16px; }}
  .cv-lines {{ font-size: 15px; color: #56708a; line-height: 2; margin-bottom: 10px; }}
  .cv-lines b {{ color: #33526e; font-weight: 600; }}
  table {{ border-collapse: collapse; margin-bottom: 14px; }}
  td {{ padding: 4px 0; font-size: 15px; color: #4a6076; }}
  td.k {{ color: #8aa4bd; width: 74px; }}
  .intro {{
    font-size: 13.5px; line-height: 1.9; color: #44586c;
    background: rgba(238,244,250,.82);
    border-left: 3px solid #a8c8e8;
    padding: 12px 16px; border-radius: 0 10px 10px 0;
    max-width: 420px;
    margin-bottom: 16px;
  }}
  .draw {{ flex: 0 0 54%; position: relative; min-height: 660px; }}
  .draw img {{
    position: absolute;
    height: 100%;
    width: auto;
    max-width: none;
    right: {shift};
    bottom: 0;
    filter: drop-shadow(0 14px 22px rgba(80,120,170,.32));
    pointer-events: none;
  }}
  .foot {{
    padding: 12px 28px 16px; font-size: 11.5px; color: #9db4c9;
    display: flex; justify-content: space-between; letter-spacing: 1px;
  }}
</style>
</head>
<body>
<div class="card">
  <div class="banner">
    <img class="title-fade" src="{aid}/assets/title_fade.png" alt="">
    <div class="word">{word}</div>
    <div class="cn">崩坏学园2 · 角色介绍</div>
  </div>
  <div class="body">
    <div class="info">
      <div class="en-name">{en}</div>
      <div class="cn-name">{cn}</div>
      <div class="cv-lines">
        <b>中文CV</b>：{cv_cn}<br>
        <b>日文CV</b>：{cv_jp}{cv_gd_line}
      </div>
      <table>
        <tr><td class="k">生日</td><td>{birthday}</td></tr>
        <tr><td class="k">年龄</td><td>{age}</td></tr>
        <tr><td class="k">身高</td><td>{height}</td></tr>
        <tr><td class="k">体重</td><td>{weight}</td></tr>
        <tr><td class="k">三围</td><td>{measurements}</td></tr>
      </table>
      <div class="intro">{intro}</div>
    </div>
    <div class="draw"><img src="{aid}/assets/role_final.png" alt="{cn} 立绘"></div>
  </div>
  <div class="foot">
    <span>数据来源：benghuai.com 官网角色介绍板块</span>
  </div>
</div>
</body>
</html>
"""


def screenshot(html_path: Path, png_path: Path):
    code = f"""
from playwright.sync_api import sync_playwright
import pathlib
html = pathlib.Path({str(html_path)!r}).resolve().as_uri()
out = pathlib.Path({str(png_path)!r}).resolve()
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={{'width':1400,'height':900}}, device_scale_factor=2)
    pg.goto(html)
    pg.wait_for_timeout(400)
    pg.query_selector('.card').screenshot(path=str(out))
    b.close()
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def build(entry):
    rid, res_id, cn, en, intro = entry
    print(f"[{rid}] 素材+语音...")
    adir = OUT / rid / "assets"
    download(f"{STATIC}/{res_id}/info.png", adir / "info.png")
    download(f"{STATIC}/{res_id}/title.png", adir / "title.png")
    if not make_role_png(rid, res_id, rid in MIRROR_IDS):
        print(f"[{rid}] 无立绘，跳过")
        return False
    make_title_fade(rid)
    download_voices(rid, res_id)

    p = PROFILES.get(rid, {})
    cv_gd_line = f"<br>\n        <b>粤语CV</b>：{p['cv_gd']}" if p.get("cv_gd") else ""
    shift = "0"
    if rid in SHIFT_RIGHT:
        total = 10 + SHIFT_EXTRA.get(rid, 0)
        shift = f"-{total}%"
    html = HTML_TMPL.format(
        aid=rid, cn=cn, en=en, word=en.split("·")[0].split()[0],
        intro=intro or "官网暂无简介文字。",
        cv_cn=p.get("cv_cn", "--"), cv_jp=p.get("cv_jp", "--"), cv_gd_line=cv_gd_line,
        birthday=p.get("birthday", "--"), age=p.get("age", "--"),
        height=p.get("height", "--"), weight=p.get("weight", "--"),
        measurements=p.get("measurements", "--"),
        shift=shift,
    )
    (OUT / f"{rid}.html").write_text(html, encoding="utf-8")

    # 环境变量 NO_SHOT=1 时只生成 HTML，不截图（供预览确认）
    if os.environ.get("NO_SHOT") == "1":
        return True
    print(f"[{rid}] 截图...")
    screenshot(OUT / f"{rid}.html", OUT / f"{rid}_card.png")
    return True


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    entries = [e for e in ROLES if not only or e[0] == only]
    print(f"共 {len(entries)} 个角色待处理（镜像：{sorted(MIRROR_IDS)}）")
    roles_json = {}
    for entry in entries:
        try:
            if build(entry):
                rid, _, cn, en, intro = entry
                roles_json[rid] = {"cn": cn, "en": en, "intro": intro,
                                   "card_png": f"{rid}_card.png",
                                   "voice_dir": f"{rid}/voice"}
        except Exception as e:
            print(f"[{entry[0]}] 失败: {e}")
    (OUT / "roles.json").write_text(
        json.dumps(roles_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成，共生成 {len(roles_json)} 张角色卡")


if __name__ == "__main__":
    main()
