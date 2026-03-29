# 018: overlay confidence閾値フィルタ テスト結果

日時: 2026-03-29

## テスト環境

- データ: `Pose2Sim/20260227-dgtw2-lab2/pose/cam01_json` (1800フレーム)
- サイズ: 1920x1080
- FPS: 30

## 1. pip install -e . (エントリーポイント更新)

```
Successfully installed pose2sim-0.10.40.dev88+g73d567c20.d20260329
```

結果: OK

## 2. CLIヘルプ確認

```
$ pose_overlay_video --help
```

`-c`/`--conf_threshold` 引数が表示された:
```
  -c CONF_THRESHOLD, --conf_threshold CONF_THRESHOLD
                        Confidence threshold (default: 0.0). Keypoints below
                        this value are hidden.
```

結果: OK

## 3. 動画生成テスト (3パターン)

### a. デフォルト (conf_threshold=0.0)

```
$ pose_overlay_video -j .../cam01_json -o /tmp/test_018_default.mp4 --size 1920x1080
```

出力:
```
JSON files: 1800
Background: 1920x1080 (black)
Output: /tmp/test_018_default.mp4
FPS: 30
Rendering: 100%|..| 1800/1800 [00:09<00:00, 192.41it/s]
Done. 1800 frames rendered in 9.4s.
  Empty frames: 0 (0.0%)
  Output: /tmp/test_018_default.mp4
```

結果: OK -- 「Confidence threshold」行は出力されない (後方互換性OK)

### b. conf_threshold=0.3

```
$ pose_overlay_video -j .../cam01_json -o /tmp/test_018_conf03.mp4 --size 1920x1080 -c 0.3
```

出力:
```
JSON files: 1800
Background: 1920x1080 (black)
Output: /tmp/test_018_conf03.mp4
FPS: 30
Confidence threshold: 0.3
Rendering: 100%|..| 1800/1800 [00:08<00:00, 209.59it/s]
Done. 1800 frames rendered in 8.6s.
  Empty frames: 0 (0.0%)
  Output: /tmp/test_018_conf03.mp4
```

結果: OK -- 「Confidence threshold: 0.3」行が表示される

### c. conf_threshold=0.7

```
$ pose_overlay_video -j .../cam01_json -o /tmp/test_018_conf07.mp4 --size 1920x1080 -c 0.7
```

出力:
```
JSON files: 1800
Background: 1920x1080 (black)
Output: /tmp/test_018_conf07.mp4
FPS: 30
Confidence threshold: 0.7
Rendering: 100%|..| 1800/1800 [00:08<00:00, 211.37it/s]
Done. 1800 frames rendered in 8.5s.
  Empty frames: 0 (0.0%)
  Output: /tmp/test_018_conf07.mp4
```

結果: OK -- 「Confidence threshold: 0.7」行が表示される

## 4. 出力ファイルサイズ

| ファイル | サイズ |
|---------|--------|
| test_018_default.mp4 (conf=0.0) | 30,247,254 bytes (28.8 MB) |
| test_018_conf03.mp4 (conf=0.3) | 30,230,257 bytes (28.8 MB) |
| test_018_conf07.mp4 (conf=0.7) | 27,447,877 bytes (26.2 MB) |

閾値が高いほどファイルサイズが小さい (描画されるキーポイントが少ないため圧縮効率が上がる)。
conf=0.7でファイルサイズが約9%減少 -- 低信頼度キーポイントが除外されていることを示す。

## 5. 後方互換性確認

- デフォルト実行時 (conf_threshold=0.0): 「Confidence threshold」行は出力されない -- OK
- 閾値指定時のみ表示される -- OK

## 総合結果: 全テストPASS
