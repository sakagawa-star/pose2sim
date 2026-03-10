# 012 2Dキーポイント推定の暴れ対策 — 機能設計書（Phase 1）

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-012-001 | 4. Phase 1 詳細設計 |

**本設計書はPhase 1（FR-012-001）の調査実行方法のみを定義する。Phase 2・3はPhase 1完了後に別途設計する。**

## 2. システム構成

### 分析スクリプト

| ファイル | 役割 |
|---------|------|
| `Pose2Sim/Utilities/keypoint_jitter_analyze.py` | 暴れ分析CLIツール |

### 既存ツールとの関係

- `pose_confidence_analyze.py`（010で作成）: 2Dキーポイントの信頼度分析。JSONの読み込みロジックを参考にする
- 本スクリプトはconfidence分析と異なり「フレーム間の移動量」に焦点を当てるため、別スクリプトとして新規作成する
- JSON読み込み部分（1フレームのOpenPose JSONからキーポイント配列を取得する処理）は`pose_confidence_analyze.py`の実装を参照・再利用する

### 依存関係

- 入力: OpenPose形式JSON（既存データ）
- 出力: 分析結果Markdown + CSV + プロット画像
- 外部依存: numpy, pandas, matplotlib（全て既にインストール済み）

## 3. 技術スタック

- Python 3.11（Pose2Sim環境）
- numpy: 数値計算
- pandas: CSV出力・集計
- matplotlib: プロット出力
- tqdm: 進捗表示
- 新規ライブラリの追加なし

## 4. Phase 1 詳細設計: 暴れ検出・分類分析

### 4.1 データフロー（2パス処理）

```
=== パス1: データ収集 ===
入力: pose/cam{NN}_json/*.json
  ↓ JSONパース
  ↓ 各フレームから抽出:
  │   - pose_keypoints_2d → reshape(26, 3) → [x, y, conf]
  │   - people[0]を使用（単一人物データセット）
  ↓ 全フレームのキーポイント配列を構築: shape (N_frames, 26, 3)
  ↓ フレーム間移動量の計算（各キーポイントごと）
  ↓ 移動量中央値の計算（各キーポイントごと）
  ↓ BB面積の計算（各フレーム）
  ↓ BB面積中央値の計算

=== パス2: 暴れ検出 ===
  ↓ 暴れ閾値 = 移動量中央値 × 5.0
  ↓ 閾値超過のフレーム・キーポイントを検出
  ↓ 原因分類（A/C/D/E）
  ↓
出力: 分析結果ドキュメント + CSV + プロット
```

### 4.2 処理ロジック

#### Step 1: 2Dキーポイント時系列の構築

```python
# JSON読み込み（pose_confidence_analyze.pyの読み込みロジックを参考）
def load_keypoints_series(cam_json_dir):
    """カメラ1台分の全フレームキーポイントを読み込む

    Args:
        cam_json_dir: cam{NN}_json/ ディレクトリのパス
    Returns:
        np.ndarray: shape (N_frames, 26, 3), dtype=float64
    """
    files = sorted(glob(os.path.join(cam_json_dir, '*.json')))
    keypoints_series = np.full((len(files), 26, 3), np.nan)

    for i, f in enumerate(tqdm(files, desc=os.path.basename(cam_json_dir))):
        with open(f) as fp:
            data = json.load(fp)
        if len(data["people"]) > 0:
            # 単一人物データセット: 最初の人物を使用
            kp = np.array(data["people"][0]["pose_keypoints_2d"]).reshape(26, 3)
            keypoints_series[i] = kp

    return keypoints_series
```

#### Step 2: フレーム間移動量の計算

```python
def compute_displacements(keypoints_series):
    """各キーポイントのフレーム間ユークリッド距離を計算

    Args:
        keypoints_series: shape (N_frames, 26, 3)
    Returns:
        displacements: shape (N_frames-1, 26), dtype=float64. NaN = 片方のconfが0.1未満
    """
    xy = keypoints_series[:, :, :2]   # (N_frames, 26, 2)
    conf = keypoints_series[:, :, 2]  # (N_frames, 26)

    diff = np.diff(xy, axis=0)  # (N_frames-1, 26, 2)
    displacements = np.sqrt(np.sum(diff**2, axis=2))  # (N_frames-1, 26)

    # 片方のconfが0.1未満の場合はNaN
    valid_prev = conf[:-1] > 0.1
    valid_curr = conf[1:] > 0.1
    valid = valid_prev & valid_curr
    displacements[~valid] = np.nan

    return displacements
```

#### Step 3: 暴れ検出

```python
def detect_jitter(displacements, multiplier=5.0):
    """暴れを検出する

    Args:
        displacements: shape (N_frames-1, 26)
        multiplier: 中央値の何倍を閾値とするか（デフォルト: 5.0）
    Returns:
        jitter_mask: shape (N_frames-1, 26), bool
        thresholds: shape (26,), 各キーポイントの閾値
        medians: shape (26,), 各キーポイントの移動量中央値
    """
    medians = np.nanmedian(displacements, axis=0)  # (26,)

    # 移動量中央値が0のキーポイント（ほぼ静止）の場合、閾値を10pxに設定
    thresholds = medians * multiplier
    thresholds[medians == 0] = 10.0

    jitter_mask = displacements > thresholds[np.newaxis, :]

    return jitter_mask, thresholds, medians
```

#### Step 4: BB面積の計算と原因分類

```python
def compute_bb_areas(keypoints_series, image_size=(1920, 1080)):
    """各フレームのBB面積を計算

    Args:
        keypoints_series: shape (N_frames, 26, 3)
    Returns:
        bb_areas: shape (N_frames,), BB面積（px^2）。全キーポイント無効時はNaN
    """
    bb_areas = np.full(keypoints_series.shape[0], np.nan)
    for i in range(keypoints_series.shape[0]):
        kp = keypoints_series[i]
        valid = kp[:, 2] > 0.1
        if valid.sum() >= 2:
            valid_xy = kp[valid, :2]
            bb_min = valid_xy.min(axis=0)
            bb_max = valid_xy.max(axis=0)
            bb_areas[i] = (bb_max[0] - bb_min[0]) * (bb_max[1] - bb_min[1])
    return bb_areas

def classify_pattern(frame_idx, kp_idx, keypoints_series, bb_areas, median_bb_area,
                     image_size=(1920, 1080)):
    """暴れの原因を分類する。A > C > D > E の優先順。

    Args:
        frame_idx: 暴れが発生したフレームインデックス（displacementsの行 = frame_idx）
                   対応するkeypoints_seriesのフレームは frame_idx + 1
        kp_idx: キーポイントインデックス
        keypoints_series: shape (N_frames, 26, 3)
        bb_areas: shape (N_frames,)
        median_bb_area: float, 同一カメラのBB面積中央値
        image_size: (width, height) in pixels
    Returns:
        str: 'A', 'C', 'D', or 'E'
    """
    kp = keypoints_series[frame_idx + 1]  # 暴れ発生フレーム
    margin = 10  # pixels
    w, h = image_size

    # パターンA: 画角外（BBが画面端に接している）
    valid = kp[:, 2] > 0.1
    if valid.sum() >= 2:
        valid_xy = kp[valid, :2]
        bb_min = valid_xy.min(axis=0)
        bb_max = valid_xy.max(axis=0)
        if (bb_min[0] < margin or bb_min[1] < margin or
            bb_max[0] > w - margin or bb_max[1] > h - margin):
            return 'A'

    # パターンC: BB面積が中央値の50%未満
    area = bb_areas[frame_idx + 1]
    if not np.isnan(area) and not np.isnan(median_bb_area) and area < median_bb_area * 0.5:
        return 'C'

    # パターンD: 低confidence
    if kp[kp_idx, 2] < 0.3:
        return 'D'

    return 'E'
```

### 4.3 CLIインターフェース

```
keypoint_jitter_analyze -p <pose_dir> [-o <output_dir>] [--multiplier <float>] [--no-plot]

引数:
  -p, --pose-dir   : poseディレクトリのパス（必須）。cam{NN}_json/ を含む親ディレクトリ
  -o, --output-dir  : 出力先ディレクトリ（デフォルト: docs/012_2d_keypoint_jitter/test_results/）
  --multiplier      : 暴れ検出閾値の倍率（デフォルト: 5.0）
  --no-plot         : プロット画像を生成しない
```

`pyproject.toml` エントリーポイント:
```
keypoint_jitter_analyze = "Pose2Sim.Utilities.keypoint_jitter_analyze:main"
```

### 4.4 出力フォーマット

#### CSV（`test_results/jitter_events.csv`）

```
camera,frame,keypoint,keypoint_idx,displacement,confidence,threshold,median_displacement,pattern
cam01,523,LWrist,9,85.3,0.21,32.5,6.5,D
cam01,524,LWrist,9,92.1,0.18,32.5,6.5,D
```

#### プロット画像

1. **暴れ頻度ヒートマップ**: カメラ(行) × キーポイント(列)、色=暴れ発生回数。保存: `jitter_heatmap.png`
2. **暴れ時confidence分布**: ヒストグラム（暴れ発生時 vs 全体）。保存: `jitter_confidence_dist.png`
3. **パターン別分布**: 積み上げ棒グラフ（カメラ別）。保存: `jitter_pattern_dist.png`
4. **移動量の時系列**: 暴れが多いキーポイント上位3つについて移動量の時系列プロット。保存: `jitter_timeseries_top3.png`

#### 分析結果ドキュメント（`phase1_results.md`）

以下のセクションを含む:
1. データ概要（フレーム数、カメラ数、キーポイント数、fps）
2. 暴れ検出パラメータ（閾値倍率、有効confidence閾値）
3. カメラ別・キーポイント別の暴れ発生数サマリテーブル
4. パターン別の集計と考察
5. confidence分布の比較
6. 最も問題のあるキーポイント上位5つの詳細分析
7. 考察と次フェーズへの示唆

### 4.5 エラーハンドリング

| エラー | 処理 |
|--------|------|
| JSONパースエラー | WARNING出力してスキップ |
| 検出人数0のフレーム | 全キーポイントをNaNとして記録 |
| 全フレームでconf < 0.1のキーポイント | 分析対象外として報告 |
| 移動量中央値が0のキーポイント | 閾値を10pxに設定（静止キーポイントの暴れも検出） |

### 4.6 境界条件

- 最初のフレーム: 移動量計算不可、スキップ
- 連続するconf < 0.1のフレーム: 間の移動量はNaN扱い
- 画面解像度: image_size引数で指定（デフォルト: 1920x1080）

### 4.7 ログ・進捗表示

- tqdmでカメラごとのフレーム読み込み進捗を表示
- 処理完了時にカメラ別の暴れ発生件数サマリを標準出力に表示

## 5. HALPE_26キーポイント名称定義

出典: `Pose2Sim/skeletons.py` のHALPE_26定義（id属性順 = JSON配列順）および `Pose2Sim/Utilities/pose_confidence_analyze.py`

**重要: JSON配列のインデックスは skeletons.py の id 属性に対応する（0=Nose, 1=LEye, ...）。TRCファイルの列順（ツリー走査順: Hip, RHip, ...）とは異なる。**

```python
# JSON配列順序（skeletons.py id属性）
HALPE_26_NAMES = [
    'Nose', 'LEye', 'REye', 'LEar', 'REar',           # 0-4
    'LShoulder', 'RShoulder', 'LElbow', 'RElbow',      # 5-8
    'LWrist', 'RWrist',                                 # 9-10
    'LHip', 'RHip', 'LKnee', 'RKnee',                 # 11-14
    'LAnkle', 'RAnkle',                                 # 15-16
    'Head', 'Neck', 'Hip',                              # 17-19
    'LBigToe', 'RBigToe', 'LSmallToe', 'RSmallToe',   # 20-23
    'LHeel', 'RHeel'                                    # 24-25
]
```

## 6. 設計判断の記録

### 採用: 移動量中央値の倍率ベースの閾値
- 理由: キーポイントごとに動きの大きさが異なる（足先 vs 体幹）ため、絶対値閾値は不適切
- 初期値: 5.0倍。探索的な値であり、Phase 1の結果に基づいて調整する
- 却下案: 固定ピクセル閾値 → 動きの速いキーポイントで偽陽性が多発

### 採用: 主作業データのみをPhase 1のスコープとする
- 理由: 単一人物データセットでは人物切り替わりによる偽陽性がなく、純粋にキーポイントの暴れを分析できる
- PortalCamデータは011のフレーム間マッチング完了後に拡張分析として検討する
- 却下案: PortalCamデータも含める → 最高confidence人物の選択で人物切り替わりが暴れとして検出される偽陽性リスク

### 採用: 2パス処理（1パス目: 統計量収集、2パス目: 暴れ検出）
- 理由: 暴れ閾値の計算に全フレームの移動量中央値が必要。BB面積中央値も同様
- 主作業データは4.3MBと小さく、全フレームのメモリ保持に問題なし
- 却下案: ストリーミング1パス処理 → 中央値の事前計算が必要で2パスは避けられない

### 採用: 別スクリプトとして新規作成（pose_confidence_analyzeの拡張ではなく）
- 理由: confidence分析は「キーポイントごとの信頼度分布」、暴れ分析は「フレーム間の移動量異常」と分析の焦点が異なる。スクリプトの責務を分離する
- JSON読み込み部分はpose_confidence_analyze.pyの実装パターンを参考にする
