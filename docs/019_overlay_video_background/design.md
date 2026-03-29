# 019: オーバーレイ動画 MP4動画背景対応 — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|--------------|
| FR-001 | 4.1 背景タイプの判定 |
| FR-002 | 4.2 動画背景のフレームループ |
| FR-003 | 4.3 フレーム数不一致の処理 |
| FR-004 | 4.4 解像度・FPS自動取得 |

## 2. システム構成

### モジュール構成

```
Pose2Sim/Utilities/pose_overlay_video.py  （既存ファイルの変更のみ）
  ├── main()      — --fpsデフォルト値をNoneに変更
  └── process()   — 背景動画対応ロジックを追加、fpsパラメータがNoneを許容するよう変更
```

変更対象は `pose_overlay_video.py` 1ファイルのみ。`common.py`, `skeletons.py`, `pyproject.toml` の変更は不要。

## 3. 技術スタック

既存と同じ。新規ライブラリの追加は不要。
- `cv2.VideoCapture`: 動画フレーム読み込み（OpenCV既存依存）

## 4. 各機能の詳細設計

### 4.1 背景タイプの判定（FR-001）

#### 処理ロジック

`process()`関数内の背景準備セクション（現行の行67-76）を以下のように変更する。

ファイル拡張子で画像/動画/不明を判定する。動画モードでは`bg`変数は使用しないため`None`を設定する:

```python
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp'}

bg = None       # 動画モードでは使用しない
bg_cap = None   # 静止画・黒背景モードでは使用しない

if background_path is not None:
    ext = os.path.splitext(background_path)[1].lower()
    if ext in VIDEO_EXTENSIONS:
        # 動画背景モード
        bg_cap = cv2.VideoCapture(background_path)
        if not bg_cap.isOpened():
            raise FileNotFoundError(f'Cannot open background video: {background_path}')
        bg_mode = 'video'
    elif ext in IMAGE_EXTENSIONS:
        # 静止画背景モード（既存動作）
        bg = cv2.imread(background_path)
        if bg is None:
            raise FileNotFoundError(f'Cannot read background image: {background_path}')
        bg_mode = 'image'
    else:
        # 拡張子不明: cv2.imreadを試行し、失敗したらcv2.VideoCaptureを試行
        bg = cv2.imread(background_path)
        if bg is not None:
            bg_mode = 'image'
        else:
            bg_cap = cv2.VideoCapture(background_path)
            if bg_cap.isOpened():
                bg_mode = 'video'
            else:
                raise FileNotFoundError(f'Cannot read background file: {background_path}')
else:
    bg_mode = 'black'
    W, H = size
    bg = np.zeros((H, W, 3), dtype=np.uint8)
```

#### 設計判断

- **採用案**: 拡張子判定 + フォールバック — 高速（ファイルを開かずに判定）かつ、未知拡張子も対応
- **却下案**: 常に`cv2.imread`→失敗なら`cv2.VideoCapture` — 画像読み込みの試行コストは低いが、動画ファイルを画像として読もうとする無駄がある。拡張子判定のほうが意図が明確

### 4.2 動画背景のフレームループ（FR-002）

#### 変更箇所

現行のフレームループ（行94-134）の構造を変更する。

#### 現行コード（静止画/黒背景）

```python
for frame_idx, f in enumerate(tqdm(files, desc='Rendering')):
    img = bg.copy()
    # ... JSON読み込み・描画 ...
```

#### 変更後コード

```python
for frame_idx, f in enumerate(tqdm(files[:n_render], desc='Rendering')):
    # 背景フレームの取得
    if bg_mode == 'video':
        ret, img = bg_cap.read()
        if not ret:
            break
    else:
        img = bg.copy()

    # ... 以降の処理（フレーム番号描画・JSON読み込み・キーポイント描画）は変更なし ...
```

動画モードでは`bg.copy()`の代わりに`bg_cap.read()`で毎フレーム新しい背景を取得する。

#### 後処理

ループ終了後、動画背景の場合は`bg_cap.release()`を呼ぶ:

```python
if bg_mode == 'video':
    bg_cap.release()
out.release()
```

### 4.3 フレーム数不一致の処理（FR-003）

#### 処理ロジック

動画背景モードの場合、レンダリングフレーム数を `min(N_v, N_j)` に制限する。

```python
if bg_mode == 'video':
    n_video_frames = int(bg_cap.get(cv2.CAP_PROP_FRAME_COUNT))
    n_render = min(n_frames, n_video_frames)
    if n_frames != n_video_frames:
        print(f'Warning: JSON files ({n_frames}) and video frames ({n_video_frames}) count mismatch. '
              f'Rendering {n_render} frames.', file=sys.stderr)
else:
    n_render = n_frames
```

ループは `files[:n_render]` でスライスする。

#### 完了時の出力

```python
print(f'Done. {n_render} frames rendered in {elapsed:.1f}s.')
```

`n_frames` → `n_render` に変更して、実際にレンダリングしたフレーム数を表示する。

### 4.4 解像度・FPS自動取得（FR-004）

#### 処理ロジック

4.1の背景判定後、VideoWriter生成前に以下を実行する。解像度取得・FPS決定・フレーム数取得を一括で行う:

```python
# 解像度とFPSの取得（4.1の背景判定直後に実行）
if bg_mode == 'video':
    W = int(bg_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(bg_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps is None:
        video_fps = bg_cap.get(cv2.CAP_PROP_FPS)
        fps = int(round(video_fps)) if video_fps > 0 else 30
elif bg_mode == 'image':
    H, W = bg.shape[:2]
    if fps is None:
        fps = 30
else:  # black
    # W, H は既にsize から設定済み
    if fps is None:
        fps = 30
```

**FPSの扱い**:
- `main()`での`--fps`引数のデフォルト値を`30`から`None`に変更する
- `process()`は`fps`パラメータに`int`または`None`を受け取る（docstringを`fps : int or None`に更新する）
- `fps`が`None`の場合: 動画背景モードでは動画のFPSを使用、それ以外は30
- `fps`が`None`でない場合（`--fps`が明示的に指定された場合）: その値を使用

**`--size`の扱い**:
- 動画背景モードでは`--size`は無視される（動画の解像度を使用）。警告は出さない（静止画背景時の`--size`無視と同じ挙動）

#### main()の変更

```python
parser.add_argument('-f', '--fps', type=int, default=None,
                    help='Frame rate (default: auto from video, or 30)')
```

#### process()シグネチャとdocstringの変更

```python
# シグネチャは変更なし（fpsは引き続き位置引数）
def process(json_dir, background_path, output_path, fps, size, conf_threshold=0.0):

# docstringの fps 行を以下に変更:
#     fps : int or None
#         Frame rate of output video. None for auto (from video, or 30).
```

`main()`から`fps=None`が渡される場合がある。`process()`内の上記ロジックでNoneをintに解決してからVideoWriterに渡す。

## 5. 変更差分の全体像

変更ファイル: `Pose2Sim/Utilities/pose_overlay_video.py` のみ

| 箇所 | 変更内容 |
|------|---------|
| 定数セクション | `VIDEO_EXTENSIONS`, `IMAGE_EXTENSIONS` 定数を追加 |
| `process()` 背景準備（行67-76） | 画像/動画/黒背景の3モード判定に変更 |
| `process()` 背景準備後 | 動画モード時の解像度・FPS・フレーム数取得を追加 |
| `process()` print出力（行78-83） | 背景表示を`video`モード対応に変更 |
| `process()` フレームループ（行94） | `files[:n_render]`にスライス、`bg.copy()`を条件分岐に変更 |
| `process()` ループ後（行136） | 動画モード時の`bg_cap.release()`を追加。既存の`out.release()`と同様にループ後で呼び出す（try/finallyパターンは既存コードに合わせて導入しない） |
| `process()` 完了時出力（行139-141） | `n_frames`→`n_render`に変更 |
| `process()` docstring | `fps`の型注釈を`int or None`に変更 |
| `main()` argparse | `--fps`のデフォルトを`None`に変更 |
| モジュールdocstring | 動画背景の使用例を追加: `pose_overlay_video -j /path/to/json_dir -b /path/to/video.mp4` |

## 6. 境界条件

| ケース | 振る舞い |
|--------|---------|
| `-b video.mp4`（動画背景） | 動画フレームごとにキーポイントを重ねた動画を出力 |
| `-b image.jpg`（静止画背景） | 現行動作と同じ |
| `-b`未指定（黒背景） | 現行動作と同じ |
| 動画フレーム数 > JSON数 | JSONファイル数分のみレンダリング。警告出力 |
| 動画フレーム数 < JSON数 | 動画フレーム数分のみレンダリング。警告出力 |
| 動画フレーム数 = JSON数 | 全フレームレンダリング。警告なし |
| 動画が開けない | `FileNotFoundError`で即座にエラー終了 |
| `--fps`未指定 + 動画背景 | 動画のFPSを使用 |
| `--fps 15` + 動画背景 | 指定値15を使用 |
| `--fps`未指定 + 静止画/黒背景 | デフォルト30を使用 |
| 未知の拡張子 | `cv2.imread`→`cv2.VideoCapture`の順でフォールバック試行 |
| 動画のFPSが0以下（メタデータ破損） | デフォルト30を使用 |

## 7. ログ・デバッグ設計

処理開始時のprint出力を動画モードに対応:
```
Background: 1920x1080 (video: /path/to/video.mp4)
FPS: 30 (from video)
```

フレーム数不一致時の警告:
```
Warning: JSON files (1800) and video frames (2000) count mismatch. Rendering 1800 frames.
```
