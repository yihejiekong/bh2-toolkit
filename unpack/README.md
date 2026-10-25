# unpack · 解包与素材导出

| 脚本 | 作用 |
|---|---|
| `apk_extract.py` | 从 APK 里解出 AssetBundle 到 `data/apk/` |
| `gzzv2.py` | 13.4+ 资源包的 GGZV2 解密，挂进 UnityPy（被其他脚本 import） |
| `bundle_decrypt.py` | 解密主数据包 `data_all.unity3d`，导出全部 TextAsset 到 `data/tsv/` |
| `unpack_assets.py` | 批量解包目录下的 bundle（处理块加密，导出对象清单） |
| `export_tables.py` | 把 `data/tsv` 里的表格统一整理成 `data/tsv_all/*.txt` |
| `export_textures.py` | 批量导出纹理（装备图标等），带尺寸过滤 |
| `export_figures.py` | 觉醒立绘：贴图名 = FigureID，同名多份时优先 1024×1024 |
| `export_faces.py` | 表情差分：`partner<NNN>` 包里的 256×256 小图 |
| `export_costume_atlas.py` | 服装拆件图集：整图 + `.atlas` 文本 |
| `pcap_scan.py` | 纯标准库 pcap/pcapng 解析，按连接导出字节流 |

## 用法要点

* 所有路径都从 `cards/paths.py` 取，可用环境变量覆盖
  （`BH2_DATA` / `MATERIAL_ROOT` / `BH2_TSV` …）。
* 需要 UnityPy 的地方都先 `import gzzv2; gzzv2.install()`，
  否则 13.4+ 的包会报 `LZ4 decompress failed: error code 110`。
* `pcap_scan.py` 不依赖 scapy：

```bash
python pcap_scan.py cap.pcap                 # 列出连接与字节数
python pcap_scan.py cap.pcap --dump 26001    # 导出该连接的上行/下行流
```

详细说明见 [../docs/01-解包与素材提取.md](../docs/01-解包与素材提取.md)。
