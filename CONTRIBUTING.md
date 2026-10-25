# 参与贡献

感谢你愿意一起把这套工具链做得更好。提之前先花两分钟看完这几条，能省掉一轮来回。

## 先看看是不是已知问题

* 先搜一遍 [Issues](https://github.com/yihejiekong/bh2-toolkit/issues)（含已关闭的），
  尤其是解包报错、卡片裁切、机器人不回消息这几类，踩过的人不少。
* 常见问题在 [docs/使用说明.md](docs/使用说明.md) 末尾有一张表，先去对一眼。

## 提交 Issue

* **Bug**：用 `Bug 报告` 模板，务必带上
  * 游戏版本（如 `13.4.8`）、系统与 Python 版本；
  * 完整报错栈（不是截图里的半行）；
  * 能复现的最小命令，例如 `python cards/batch.py --ids 897`。
* **功能建议**：用 `功能建议` 模板，说清楚「现在的做法」和「你希望的做法」。
* 一句「不 work」很难定位，请尽量给出可复现的输入。

## 提交 Pull Request

1. Fork 本仓库，从 `main` 切一个分支：`git checkout -b fix/atlas-crop`；
2. 改完自己跑一遍：

   ```bash
   python -m compileall -q unpack cards bot
   python cards/batch.py --ids 897        # 有素材的话，出图验证
   ```

3. 提交信息用 `类型(范围): 说明` 的格式，例如
   `fix(cards): 服装图集裁切串到邻件`、`docs: 补充热更资源目录`；
4. 开 PR，说明「改了什么 / 为什么 / 怎么验证的」，有前后对比图更好。

## 代码约定

* **不要提交任何游戏素材**：`materials/`、`data/`、`tables/*.xlsx`、`*.db`、`*.pcap`
  都已在 `.gitignore` 里，PR 里带上来会被直接关掉；
* **不要提交凭据**：`.env`、`servers.json`、Cookie、登录帧、Token 一律不入库，
  需要配置的都走环境变量或本地文件；
* 路径一律用 `cards/paths.py` 里的 `P.TABLES / P.MATERIALS / P.DATA`，不要写死本机绝对路径；
* 脚本里读写含中文的文件统一 `encoding='utf-8'`；
* 新脚本加一句文件头注释说明用途和用法，方便别人 `--help` 之前先看懂。

## 不接受的改动

* 任何形式的商业化分发、付费代查、批量刷接口；
* 把协议层做成「免登录查任意账号」之类的滥用工具；
* 提交别人的账号凭据或抓包文件。

## 许可

提交即表示同意你的代码以 [MIT](LICENSE) 许可发布。
