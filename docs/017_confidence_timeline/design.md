# 017: キーポイント信頼度タイムラインCLIツール — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|--------------|
| FR-001 | 4.1 CLI引数パース |
| FR-002 | 4.2 JSONファイル読み込み |
| FR-003 | 4.3 CSV出力 |
| FR-004 | 4.4 PNGプロット出力 |

## 2. システム構成

### モジュール構成

```
Pose2Sim/Utilities/confidence_timeline.py  （新規作成）
  ├── main()      — CLIエントリーポイント
  └── process()   — メイン処理（JSON読み込み→CSV出力→PNG出力）

依存（import文）:
  import numpy as np
  import matplotlib.pyplot as plt
```

### ディレクトリ構成

```
Pose2Sim/Utilities/confidence_timeline.py   # 新規ファイル
pyproject.toml                               # エントリーポイント追加
```

## 3. 技術スタック

- Python 3.9+
- NumPy: 配列操作 — Pose2Sim既存依存
- matplotlib: プロット生成 — Pose2Sim既存依存
- tqdm: プログレスバー — Pose2Sim既存依存

新規ライブラリの追加は不要。

## 4. 各機能の詳細設計

### 4.1 CLI引数パース（FR-001）

#### 引数定義

| 引数 | 短縮 | 必須 | デフォルト | 説明 |
|------|------|------|-----------|------|
| `--json_dir` | `-j` | Yes | — | 入力JSONディレクトリ |
| `--keypoints` | `-k` | No | `Nose,Neck,RShoulder,LShoulder` | 表示キーポイント名（カンマ区切り） |
| `--output` | `-o` | No | `{json_dir}_conf_timeline` | 出力ディレクトリ |
| `--threshold` | `-t` | No | None | 閾値線（カンマ区切り、例: `0.3,0.5`）。未指定時は閾値線なし |

#### キーポイント名からJSONインデックスへの変換

HALPE_26のキーポイント名とJSON配列インデックスの対応表をスクリプト内に定数として定義する:

```python
HALPE_26_INDICES = {
    'Nose': 0, 'LEye': 1, 'REye': 2, 'LEar': 3, 'REar': 4,
    'LShoulder': 5, 'RShoulder': 6, 'LElbow': 7, 'RElbow': 8,
    'LWrist': 9, 'RWrist': 10, 'LHip': 11, 'RHip': 12,
    'LKnee': 13, 'RKnee': 14, 'LAnkle': 15, 'RAnkle': 16,
    'Head': 17, 'Neck': 18, 'Hip': 19,
    'LBigToe': 20, 'RBigToe': 21, 'LSmallToe': 22, 'RSmallToe': 23,
    'LHeel': 24, 'RHeel': 25
}
```

`-k`引数のキーポイント名がこの辞書に存在しない場合、`ValueError`で即座にエラー終了し、利用可能なキーポイント名の一覧を表示する。

#### 設計判断

- **CLI引数 `-j`/`--json_dir`**: `pose_overlay_video.py`と同じパターンを採用。JSON入力専用であることを明示する。`pose_extract_person.py`の`-i`/`--input`は汎用的な入力を示すが、本ツールとpose_overlay_videoはJSON専用のため`-j`で統一する。

#### エントリーポイント

`pyproject.toml`に本ツールのエントリーポイントのみ追加する:
```
confidence_timeline = "Pose2Sim.Utilities.confidence_timeline:main"
```

### 4.2 JSONファイル読み込み（FR-002）

#### ファイル列挙・ソート

```python
files = sorted(glob(os.path.join(json_dir, '*.json')))
```

#### データ構造

収集データはリストに蓄積する:
```python
rows = []  # list of (frame_idx, person_idx, keypoint_name, confidence)
```

#### 処理ロジック

```python
for frame_idx, f in enumerate(tqdm(files, desc='Reading')):
    with open(f) as fp:
        data = json.load(fp)
    for person_idx, person in enumerate(data.get('people', [])):
        kps = person.get('pose_keypoints_2d', [])
        if len(kps) < 26 * 3:
            continue
        kp = np.array(kps[:26 * 3]).reshape(26, 3)  # HALPE_26の26キーポイント分のみ
        for name, idx in target_keypoints.items():
            rows.append((frame_idx, person_idx, name, float(kp[idx, 2])))
```

#### エラーハンドリング

- JSONディレクトリが空: `FileNotFoundError`で即座にエラー終了
- JSONパースエラー: 警告を`stderr`に出力し、そのフレームをスキップ
- `pose_keypoints_2d`の要素数が26*3未満: その人物をスキップ

### 4.3 CSV出力（FR-003）

#### データフロー

- 入力: `rows`リスト
- 出力: `{output_dir}/confidence_timeline.csv`

#### ファイル形式

```
frame,person,keypoint,confidence
0,0,Nose,0.892
0,0,Neck,0.845
0,0,RShoulder,0.781
0,0,LShoulder,0.756
0,1,Nose,0.213
...
```

#### 処理ロジック

```python
with open(csv_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['frame', 'person', 'keypoint', 'confidence'])
    writer.writerows(rows)
```

### 4.4 PNGプロット出力（FR-004）

#### データフロー

- 入力: `rows`リスト、キーポイント名リスト、閾値リスト（任意）
- 出力: `{output_dir}/confidence_timeline.png`

#### 処理ロジック

```python
fig, axes = plt.subplots(n_keypoints, 1, figsize=(14, 2.5 * n_keypoints), sharex=True)
if n_keypoints == 1:
    axes = [axes]

for ax, name in zip(axes, keypoint_names):
    # このキーポイントのデータを抽出
    frames = [r[0] for r in rows if r[2] == name]
    confs = [r[3] for r in rows if r[2] == name]
    ax.scatter(frames, confs, s=1, alpha=0.5)
    ax.set_ylabel(name)
    ax.set_ylim(-0.05, 1.05)

    # 閾値線
    if thresholds:
        for th in thresholds:
            ax.axhline(y=th, color='r', linestyle='--', alpha=0.5, label=f'{th}')
        ax.legend(loc='lower right', fontsize=8)

axes[-1].set_xlabel('Frame')
fig.suptitle('Keypoint Confidence Timeline')
plt.tight_layout(rect=[0, 0, 1, 0.96])  # suptitleとの干渉を回避
fig.savefig(png_path, dpi=150)
plt.close(fig)
```

#### 設計判断

- **採用**: 散布図（scatter） — 同一フレームに複数人物の点が重なるため、散布図が適切
- **却下**: 折れ線グラフ — 人物の追跡をしないため、線で繋ぐ意味がない

### 4.5 境界条件

| ケース | 振る舞い |
|--------|---------|
| JSONディレクトリが空（*.jsonが0件） | `FileNotFoundError`で即座にエラー終了 |
| 全フレームで人物検出ゼロ | 空のCSVと空のプロットを出力する |
| JSONパースエラー | 警告を`stderr`に出力し、そのフレームをスキップ |
| `-k`に不正なキーポイント名 | `ValueError`で即座にエラー終了。利用可能な名前一覧を表示 |
| 出力ディレクトリが既に存在する | そのまま使用する。既存ファイル（CSV/PNG）は上書きする |
| 出力ディレクトリが存在しない | `os.makedirs(output_dir, exist_ok=True)`で作成する |
| `-t`の値が数値でない | `ValueError`で即座にエラー終了 |
| キーポイント指定が1個のみ | サブプロット1段で正常に動作する |

## 5. ファイル・ディレクトリ設計

### 出力パス規約

- デフォルト出力ディレクトリ: `{json_dir}_conf_timeline`
- 出力ファイル:
  - `confidence_timeline.csv`
  - `confidence_timeline.png`

## 6. インターフェース定義

### `main()`
```python
def main():
    '''CLI entry point.'''
```

### `process(json_dir: str, keypoint_names: list[str], output_dir: str, thresholds: list[float] | None)`
```python
def process(json_dir, keypoint_names, output_dir, thresholds):
    '''Analyze keypoint confidence timeline and output CSV + PNG.

    Parameters
    ----------
    json_dir : str
        Path to directory containing per-frame JSON files.
    keypoint_names : list[str]
        List of keypoint names to analyze.
    output_dir : str
        Path to output directory.
    thresholds : list[float] or None
        Threshold values for horizontal reference lines. None for no lines.
    '''
```

## 7. ログ・デバッグ設計

- 処理開始時: JSON数、対象キーポイント、出力ディレクトリを`print`で表示
- 処理完了時: 処理フレーム数、総データ点数、処理時間、出力ファイルパスを`print`で表示
- JSONパースエラー: `print(f'Warning: ...', file=sys.stderr)`で警告
