# 018: オーバーレイ動画 confidence閾値フィルタ — 機能設計書

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|--------------|
| FR-001 | 4.1 CLI引数の追加 |
| FR-002 | 4.2 confidenceフィルタリング |
| FR-003 | 4.3 骨格線の連動非表示（既存ロジック確認） |

## 2. システム構成

### モジュール構成

```
Pose2Sim/Utilities/pose_overlay_video.py  （既存ファイルの変更のみ）
  ├── main()      — CLI引数に --conf_threshold を追加
  └── process()   — conf_threshold パラメータを追加、フィルタリングロジックを変更
```

変更対象は `pose_overlay_video.py` 1ファイルのみ。`common.py`, `skeletons.py`, `pyproject.toml` の変更は不要。

## 3. 技術スタック

既存と同じ。新規ライブラリの追加は不要。

## 4. 各機能の詳細設計

### 4.1 CLI引数の追加（FR-001）

#### 変更箇所

`main()`関数の`argparse`セクションに1行追加する。

#### 引数定義

| 引数 | 短縮 | 必須 | 型 | デフォルト | 説明 |
|------|------|------|-----|-----------|------|
| `--conf_threshold` | `-c` | No | float | 0.0 | confidence閾値。この値未満のキーポイントを描画しない |

#### 処理ロジック

`main()`内で`args.conf_threshold`を`process()`に渡す:

```python
# main()内のargparse追加
parser.add_argument('-c', '--conf_threshold', type=float, default=0.0,
                    help='Confidence threshold (default: 0.0). Keypoints below this value are hidden.')

# process()呼び出しに追加
process(json_dir, args.background, output_path, args.fps, size, args.conf_threshold)
```

#### バリデーション

バリデーションは行わない。0.0未満や1.0超の値が渡されても、動作上の問題はない（0未満→全キーポイント描画、1超→全キーポイント非表示）。

#### 設計判断

- **採用案**: バリデーションなし — 範囲外の値でも論理的に正しい結果が出る（全描画 or 全非表示）。不要なエラーで使い勝手を下げない
- **却下案**: 0.0〜1.0の範囲チェック — 範囲外でも害がなく、ユーザーにエラーを見せる必要がない

### 4.2 confidenceフィルタリング（FR-002）

#### 変更箇所

`process()`関数のシグネチャと、JSON読み込みループ内のマスク条件。

#### process()シグネチャの変更

```python
# 変更前
def process(json_dir, background_path, output_path, fps, size):

# 変更後
def process(json_dir, background_path, output_path, fps, size, conf_threshold=0.0):
```

#### フィルタリングロジック

現行コード（行115-116）:
```python
mask = kp[:, 2] <= 0
kp[mask, :2] = np.nan
```

変更後:
```python
mask = kp[:, 2] < conf_threshold
kp[mask, :2] = np.nan
```

**変更点**: `<= 0` → `< conf_threshold`

**後方互換性の確認**:
- `conf_threshold=0.0`（デフォルト）の場合: `kp[:, 2] < 0.0` → confidence=0のキーポイントはフィルタされない
- 現行コードは `kp[:, 2] <= 0` でconfidence=0もNaN化している
- **差異**: confidence=0.0のキーポイントの扱いが変わる（現行: NaN化、変更後: 描画される）
- **影響**: confidence=0.0はRTMposeの出力では「検出されていない」を意味するため、座標は(0,0)である。左上隅に小さな点が描画されるが、実用上は問題にならない
- **対策**: `<=` ではなく `<` を使い、かつ `conf_threshold` のデフォルトを0.0にするのではなく、別途confidence=0を特別扱いする

**修正版フィルタリングロジック（後方互換性を保証）**:
```python
mask = (kp[:, 2] <= 0) | (kp[:, 2] < conf_threshold)
kp[mask, :2] = np.nan
```

これにより:
- confidence=0は常にNaN化（現行動作を維持）
- conf_threshold=0.0: 現行と完全に同じ出力
- conf_threshold=0.3: confidence=0 + confidence < 0.3 をNaN化

#### 設計判断

- **採用案**: `(kp[:, 2] <= 0) | (kp[:, 2] < conf_threshold)` — confidence=0の特別扱いを維持しつつ閾値フィルタを追加。後方互換性を完全に保証
- **却下案**: 単純に `kp[:, 2] < conf_threshold` に変更 — デフォルト0.0でconfidence=0のキーポイントが描画されてしまい、後方互換性が崩れる

### 4.3 骨格線の連動非表示（FR-003）

追加実装は不要。既存の`draw_skel()`（`common.py:1356`）が以下の条件でボーンをスキップする:

```python
if not None in ids and not (np.isnan(x[ids[0]]) or np.isnan(y[ids[0]]) or np.isnan(x[ids[1]]) or np.isnan(y[ids[1]])):
```

座標がNaNのキーポイントを端点とする骨格線は描画されない。FR-002でNaN化することで自動的に実現される。

## 5. 変更差分の全体像

変更ファイル: `Pose2Sim/Utilities/pose_overlay_video.py` のみ

| 行（目安） | 変更内容 |
|-----------|---------|
| 42 | `process()`シグネチャに`conf_threshold=0.0`を追加 |
| 115 | マスク条件を `(kp[:, 2] <= 0) \| (kp[:, 2] < conf_threshold)` に変更 |
| 76付近 | printにconfidence閾値情報を追加 |
| 142-154 | `argparse`に`-c`/`--conf_threshold`引数を追加 |
| 176 | `process()`呼び出しに`args.conf_threshold`を追加 |

## 6. 境界条件

| ケース | 振る舞い |
|--------|---------|
| conf_threshold=0.0（デフォルト） | 現行動作と完全に同じ出力 |
| conf_threshold=0.3 | confidence < 0.3 のキーポイントとその関連骨格線が非表示 |
| conf_threshold=1.0 | confidence=1.0のキーポイントのみ描画（ほぼ全非表示） |
| conf_threshold=-1.0 | 全キーポイント描画（confidence=0は既存ロジックでNaN化） |
| conf_threshold=2.0 | 全キーポイント非表示（背景+フレーム番号のみ） |
| 全キーポイントが閾値未満のフレーム | 空フレーム（背景+フレーム番号のみ）として描画 |

## 7. ログ・デバッグ設計

処理開始時のprint出力に閾値情報を追加:
```
Confidence threshold: 0.3
```

conf_threshold=0.0（デフォルト）の場合はこの行を出力しない（現行出力と同じ）。
