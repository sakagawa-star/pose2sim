# 016: 2Dキーポイントオーバーレイ動画生成ツール — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|--------------|
| FR-001 | 4.1 CLI引数パース |
| FR-002 | 4.2 JSONファイル読み込み |
| FR-003 | 4.3 背景画像の準備 |
| FR-004 | 4.4 キーポイント・骨格の描画 |
| FR-005 | 4.5 動画書き出し |
| FR-006 | 4.4 キーポイント・骨格の描画（フレーム番号描画を含む） |

## 2. システム構成

### モジュール構成

```
Pose2Sim/Utilities/pose_overlay_video.py  （新規作成）
  ├── main()      — CLIエントリーポイント
  └── process()   — メイン処理（JSON読み込み→描画→動画出力）

依存（import文）:
  from Pose2Sim.common import draw_skel, draw_keypts, colors, thickness
  from Pose2Sim.skeletons import HALPE_26
```

### ディレクトリ構成

```
Pose2Sim/Utilities/pose_overlay_video.py   # 新規ファイル
pyproject.toml                              # エントリーポイント追加
```

## 3. 技術スタック

- Python 3.9+
- OpenCV（cv2）: 画像読み込み、描画、VideoWriter — Pose2Sim既存依存
- NumPy: 配列操作 — Pose2Sim既存依存
- matplotlib: `draw_keypts()`が`plt.get_cmap()`でカラーマップ取得に使用 — Pose2Sim既存依存
- tqdm: プログレスバー — Pose2Sim既存依存
- anytree: skeletons.pyのモデル走査に使用（本ツールは直接importしない）— Pose2Sim既存依存

新規ライブラリの追加は不要。

## 4. 各機能の詳細設計

### 4.1 CLI引数パース（FR-001）

#### データフロー

- 入力: コマンドライン引数
- 出力: パース済み引数オブジェクト

#### 引数定義

| 引数 | 短縮 | 必須 | デフォルト | 説明 |
|------|------|------|-----------|------|
| `--json_dir` | `-j` | Yes | — | 入力JSONディレクトリ |
| `--background` | `-b` | No | None | 背景画像パス。未指定時は黒背景 |
| `--output` | `-o` | No | `{json_dir}_overlay.mp4` | 出力動画パス |
| `--fps` | `-f` | No | 30 | 出力動画のフレームレート |
| `--size` | `-s` | No | `1920x1080` | 画像サイズ（`WxH` 形式）。背景画像指定時は無視 |

#### エントリーポイント

`pyproject.toml`に追加:
```
pose_overlay_video = "Pose2Sim.Utilities.pose_overlay_video:main"
```

### 4.2 JSONファイル読み込み（FR-002）

#### ファイル列挙・ソート

JSONファイルの列挙とソートは既存ツール（`pose_extract_person.py`）と同じ方法を使用する:
```
files = sorted(glob(os.path.join(json_dir, '*.json')))
```
- `glob` で `*.json` のみを列挙（非JSONファイルは自動的に除外される）
- `sorted()` で辞書順ソート（OpenPoseの `{prefix}_{frame:06d}.json` 形式ではフレーム順と一致する）

#### データフロー

- 入力: JSONファイルパス（1ファイル）
- 出力: `(X_list, Y_list, scores_list)` — 各要素はリスト（人物数分）
  - `X_list`: list of np.ndarray, 各shape=(26,) — x座標（JSON配列のid順）
  - `Y_list`: list of np.ndarray, 各shape=(26,) — y座標
  - `scores_list`: list of np.ndarray, 各shape=(26,) — 信頼度

#### 処理ロジック

1フレーム分のJSON読み込みは `process()` 内のループで行う。個別の読み込み関数は作らない。HALPE_26（26キーポイント）前提。

```
data = json.load(f)
people = data.get('people', [])
X_list, Y_list, scores_list = [], [], []
for person in people:
    kps = person.get('pose_keypoints_2d', [])
    if len(kps) < 26 * 3:
        continue
    kp = np.array(kps[:26 * 3]).reshape(26, 3)  # HALPE_26の26キーポイント分のみ使用
    # 信頼度0のキーポイントはNaNに置換（描画関数がNaNをスキップする）
    mask = kp[:, 2] <= 0
    kp[mask, :2] = np.nan
    X_list.append(kp[:, 0])
    Y_list.append(kp[:, 1])
    scores_list.append(kp[:, 2])
```

**注意**: `draw_skel()` と `draw_keypts()` はX, Yをリスト（人物数分のリスト）として受け取る。座標はJSON配列の**id属性順**（0=Nose, 1=LEye, ... 19=Hip）。`draw_skel()`はノードのid属性でインデックスアクセスするため、この順序で正しく動作する。

#### エラーハンドリング

- JSONパースエラー: 警告を出力し、そのフレームは空（背景のみ）で書き出す
- people配列が空またはキーポイント不足: 空フレームとして扱う（背景のみ）

### 4.3 背景画像の準備（FR-003）

#### データフロー

- 入力: 背景画像パス（str or None）、画像サイズ（tuple[int, int] or None）
- 出力: BGR画像（numpy.ndarray, shape=(H,W,3), dtype=uint8）

#### 処理ロジック

**背景画像指定あり**:
```
bg = cv2.imread(background_path)
if bg is None:
    raise FileNotFoundError(f'Cannot read background image: {background_path}')
# --size 引数は無視（画像の実サイズを使用）
```

**背景画像指定なし**:
```
# --size で指定されたサイズ、未指定時はデフォルト1920x1080
bg = np.zeros((H, W, 3), dtype=np.uint8)
```

### 4.4 キーポイント・骨格の描画（FR-004, FR-006）

#### データフロー

- 入力: 背景画像、X_list, Y_list, scores_list、フレームインデックス
- 出力: 描画済み画像（numpy.ndarray）

#### 処理ロジック

```
img = bg.copy()

# FR-006: フレーム番号描画
cv2.putText(img, f'Frame: {frame_idx}', (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)

# FR-004: キーポイント・骨格描画（複数人物を全員描画）
if X_list:  # 検出人物がある場合のみ
    img = draw_keypts(img, X_list, Y_list, scores_list, cmap_str='RdYlGn')
    img = draw_skel(img, X_list, Y_list, HALPE_26)
```

`draw_bounding_box()` は使用しない。バウンディングボックスは本ツールの目的（キーポイントの挙動確認）には不要であり、画面が煩雑になる。

#### 設計判断

- **却下案**: `draw_bounding_box()` も呼ぶ → キーポイントの挙動確認が目的なので不要。画面がうるさくなる
- **採用案**: `draw_keypts()` + `draw_skel()` のみ

#### パフォーマンス考慮

`draw_keypts()`は内部で毎回`plt.get_cmap(cmap_str)`を呼ぶが、これは既存の`common.py`の関数であり本ツールのスコープ外。`plt.get_cmap()`自体はmatplotlib内部でキャッシュされるため、10万フレームでも実質的なオーバーヘッドは無視できる。

### 4.5 動画書き出し（FR-005）

#### データフロー

- 入力: 描画済みフレーム画像のシーケンス、FPS、出力パス
- 出力: MP4動画ファイル

#### 処理ロジック

```
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
H, W = bg.shape[:2]
out = cv2.VideoWriter(output_path, fourcc, fps, (W, H))

for frame_idx, json_file in enumerate(tqdm(files, desc='Rendering')):
    # JSON読み込み → 描画 → 書き出し
    ...
    out.write(img)

out.release()
```

#### 設計判断

- **採用**: `mp4v`コーデック — OpenCV標準搭載、追加バックエンド不要
- **却下**: `h264` — ffmpegバックエンド必要で環境依存

#### エラーハンドリング

- VideoWriter作成失敗（コーデック不在等）: `out.isOpened()` で確認し、Falseなら即座にエラー終了

### 4.6 境界条件

| ケース | 振る舞い |
|--------|---------|
| JSONディレクトリが空（*.jsonが0件） | `FileNotFoundError` で即座にエラー終了。動画ファイルは作成しない |
| 全フレームで人物検出ゼロ | 全フレーム背景のみ（フレーム番号のみ描画）の動画を出力する |
| JSONパースエラー（破損ファイル） | 警告を`stderr`に出力し、そのフレームは空（背景+フレーム番号のみ）で描画する。処理を中断しない |
| `pose_keypoints_2d` の要素数が26*3未満 | その人物をスキップする（他の人物がいれば描画する） |
| `pose_keypoints_2d` の要素数が26*3超（例: COCO_133モデル） | 先頭26*3要素のみ使用（`kps[:78]`でスライス） |
| `pose_keypoints_2d` キーが存在しない人物 | `person.get('pose_keypoints_2d', [])`で空リストとなり、要素数不足でスキップされる |
| 背景画像が読み込めない | `FileNotFoundError` で即座にエラー終了 |
| `--size` の形式が不正 | `ValueError` で即座にエラー終了。メッセージで `WxH` 形式を案内 |

## 5. ファイル・ディレクトリ設計

### 出力パス規約

- デフォルト出力パス: `{json_dir}_overlay.mp4`
  - 例: 入力 `/data/cam01_json` → 出力 `/data/cam01_json_overlay.mp4`
- `-o` で任意のパスを指定可能

## 6. インターフェース定義

### `main()`
```python
def main():
    '''CLI entry point.'''
```
引数なし。`argparse`でコマンドライン引数を処理。

### `process(json_dir: str, background_path: str | None, output_path: str, fps: int, size: tuple[int, int])`
```python
def process(json_dir, background_path, output_path, fps, size):
    '''Generate overlay video from JSON keypoints and background image.

    Parameters
    ----------
    json_dir : str
        Path to directory containing per-frame JSON files.
    background_path : str or None
        Path to background image. None for black background.
    output_path : str
        Path to output MP4 video.
    fps : int
        Frame rate of output video.
    size : tuple[int, int]
        (width, height) of the video. Ignored when background_path is provided.
    '''
```

## 7. ログ・デバッグ設計

- 処理開始時: JSON数、背景画像サイズ、出力パス、FPSを`print`で表示
- 処理完了時: 処理フレーム数、空フレーム数、処理時間を`print`で表示
- JSONパースエラー: `print(f'Warning: ...', file=sys.stderr)` で警告
