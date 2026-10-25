# unpack · 解包与素材导出

| 脚本 | 作用 |
|---|---|
| `apk_extract.py` | 从 APK / 设备目录里解出 AssetBundle 到 `data/` |
| `gzzv2.py` | 13.4+ 资源包的 GGZV2 块解密，可挂进 UnityPy（被其他脚本 import） |
| `unpack_assets.py` | **主流程第一步**：把 GGZV2 加密的包改写成 UnityPy 能直接读的明文包，输出 `data/packs_dec/` |
| `export_tables.py` | 读 `data/packs_dec/data_all.unity3d`，把全部 TextAsset 落成 `data/tsv_all/*.txt` |
| `export_textures.py` | 批量导出纹理（装备图标等），带尺寸过滤 |
| `export_figures.py` | 觉醒立绘：贴图名 = FigureID，同名多份时优先 1024×1024 |
| `export_faces.py` | 表情差分：`partner<NNN>` 包里的 256×256 小图 |
| `export_costume_atlas.py` | 服装拆件图集：整图 + `.atlas` 文本 |
| `pcap_scan.py` | 纯标准库 pcap/pcapng 解析，按连接导出字节流 |
| `bundle_decrypt.py` | **仅 13.4.1 及更早**：整包 AES-256-CBC + 逐块 AES/LZ4HC，解 `data_all` 到 TSV |

## 推荐顺序

```bash
python unpack/unpack_assets.py data/raw/data_all.unity3d   # 或传整个目录
python unpack/export_tables.py                             # -> data/tsv_all/
python unpack/export_figures.py                            # -> data/faces_src/觉醒立绘（示例）
```

## 用法要点

* 所有路径都从 `cards/paths.py` 取，可用环境变量覆盖
  （`BH2_DATA` / `MATERIAL_ROOT` / `BH2_TSV` …）。
* 直接 `UnityPy.load()` 读**原始**包时必须先 `import gzzv2; gzzv2.install()`，
  否则 13.4+ 的包会报 `LZ4 decompress failed: error code 110`；
  读 `data/packs_dec/` 下的明文包则不需要。
* `export_tables.py` / `export_figures.py` / `export_faces.py` 读的都是
  `data/packs_dec/`，所以不必再挂 gzzv2。
* `pcap_scan.py` 不依赖 scapy：

```bash
python pcap_scan.py cap.pcap                 # 列出连接与字节数
python pcap_scan.py cap.pcap --dump 26001    # 导出该连接的上行/下行流
```

详细说明见 [../docs/01-解包与素材提取.md](../docs/01-解包与素材提取.md)。
