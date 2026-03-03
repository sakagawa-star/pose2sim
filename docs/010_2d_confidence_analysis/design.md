# 010: 2Dキーポイント信頼度分析 — 機能設計書

## 1. アーキテクチャ

`trc_evaluate.py`と同じ階層構造に準拠する:

```
main()                              # argparse, CLIエントリーポイント
└── analyze_confidence()            # オーケストレータ（全体制御）
    ├── load_pose_data()            # データ読み込み層
    │   └── load_camera_data()      # 1カメラ分のJSON読み込み
    ├── compute_statistics()        # 分析1: 統計量算出
    ├── compute_band_distribution() # 分析2: 帯域分布算出
    ├── simulate_threshold()        # 閾値引き上げシミュレーション
    ├── format_report()             # コンソールレポート生成
    ├── save_csv()                  # CSV出力
    └── save_heatmaps()            # ヒートマップ画像出力
```

## 2. データ構造

### 入力データ構造
```python
# load_pose_data() の戻り値
confidence_data: dict[str, np.ndarray]
# key: カメラ名 ("cam01", "cam02", ...)
# value: shape=(n_frames, 26) の信頼度行列
```

### キーポイント名定数
```python
HALPE_26_NAMES = [
    'Nose', 'LEye', 'REye', 'LEar', 'REar',
    'LShoulder', 'RShoulder', 'LElbow', 'RElbow', 'LWrist', 'RWrist',
    'LHip', 'RHip', 'LKnee', 'RKnee', 'LAnkle', 'RAnkle',
    'Head', 'Neck', 'Hip',
    'LBigToe', 'RBigToe', 'LSmallToe', 'RSmallToe', 'LHeel', 'RHeel'
]
```

### 帯域定義定数
```python
CONFIDENCE_BANDS = [
    (0.0, 0.4, 'low'),        # 現閾値で除外
    (0.4, 0.6, 'danger'),     # 危険ゾーン
    (0.6, 0.8, 'medium'),     # 中信頼
    (0.8, 1.0, 'high'),       # 高信頼
    (1.0, float('inf'), 'very_high')  # 1.0超
]
```

## 3. 各関数の設計

### `load_camera_data(cam_dir: Path) -> np.ndarray`
- `cam_dir` 内の全JSONファイルをソート順に読み込む
- 各JSONから `people[0]['pose_keypoints_2d']` を取得
- confidence値（インデックス2, 5, 8, ...）を抽出
- 戻り値: `np.ndarray` shape=(n_frames, 26)

### `load_pose_data(pose_dir: Path) -> dict[str, np.ndarray]`
- `pose_dir` 内の `cam*_json` ディレクトリを glob で検出
- 各カメラについて `load_camera_data()` を呼び出す
- カメラ名順にソートして返す

### `compute_statistics(confidence_data, threshold) -> dict`
- 各カメラ×キーポイントについて以下を算出:
  - mean, median, std, min, max
  - percentiles: 5th, 25th, 75th, 95th
  - below_threshold_rate: 閾値未満のフレーム割合
- 全カメラ平均（キーポイントごと）も算出
- 戻り値: ネストされたdict `{cam: {kp_idx: {stat_name: value}}}`

### `compute_band_distribution(confidence_data, bands) -> dict`
- 各カメラ×キーポイントについて各帯域のフレーム数・割合を算出
- 戻り値: `{cam: {kp_idx: {band_name: {'count': int, 'rate': float}}}}`

### `simulate_threshold(confidence_data, thresholds=[0.4, 0.5, 0.6]) -> dict`
- 各閾値について、各カメラ×キーポイントの除外フレーム割合を算出
- 閾値引き上げによる追加除外率（差分）も算出
- 戻り値: `{threshold: {cam: {kp_idx: exclusion_rate}}}`

### `format_report(statistics, band_dist, threshold_sim) -> str`
- 分析1サマリー: キーポイント×カメラの平均信頼度テーブル（26行×4列）
- 分析2サマリー: 帯域分布の概要（カメラ別の危険ゾーン割合）
- 問題キーポイント: 平均信頼度が全体の下位25%に入るカメラ×キーポイントの一覧
- 閾値シミュレーション: 0.4→0.5, 0.4→0.6 での追加除外数

### `save_csv(statistics, band_dist, output_dir: Path)`
- `confidence_statistics.csv`: 統計量（1行 = 1カメラ × 1キーポイント）
  - カラム: `camera, keypoint, mean, median, std, min, max, p5, p25, p75, p95, below_threshold_rate`
- `confidence_band_distribution.csv`: 帯域分布（1行 = 1カメラ × 1キーポイント）
  - カラム: `camera, keypoint, low_count, low_rate, danger_count, danger_rate, medium_count, medium_rate, high_count, high_rate, very_high_count, very_high_rate`

### `save_heatmaps(statistics, band_dist, output_dir: Path)`
- `heatmap_mean_confidence.png`: 平均信頼度ヒートマップ（Y軸=キーポイント26個, X軸=カメラ4台）
  - カラーマップ: coolwarm（低信頼=青、高信頼=赤）
  - セル内に数値を表示
- `heatmap_danger_zone_rate.png`: 危険ゾーン（0.4-0.6）割合ヒートマップ
  - カラーマップ: Reds（高割合=濃い赤）
  - セル内にパーセンテージを表示

### `analyze_confidence(pose_dir, threshold, output_dir, no_plot) -> dict`
- 上記関数を順に呼び出すオーケストレータ
- 戻り値: `{'statistics': ..., 'band_distribution': ..., 'threshold_simulation': ...}`

## 4. 出力例（コンソールレポートのイメージ）

```
=== 2D Keypoint Confidence Analysis ===
Pose directory: Pose2Sim/20260227-dgtw2-lab2/pose
Cameras: 4 (cam01, cam02, cam03, cam04)
Total frames: 7187
Threshold: 0.4

--- Analysis 1: Mean Confidence per Camera x Keypoint ---
Keypoint       cam01   cam02   cam03   cam04   avg
Nose           0.872   0.913   0.845   0.921   0.888
LEye           0.834   0.891   0.812   0.905   0.861
...
LWrist         0.623   0.712   0.587   0.734   0.664  ★
...

--- Analysis 2: Confidence Band Distribution ---
Camera   <0.4    0.4-0.6   0.6-0.8   0.8-1.0   >1.0
cam01    0.1%    8.3%      22.1%     61.2%     8.3%
cam02    0.0%    4.2%      18.7%     68.4%     8.7%
cam03    0.2%    11.5%     25.3%     55.8%     7.2%
cam04    0.0%    2.1%      15.4%     73.2%     9.3%

--- Danger Zone (0.4-0.6) Hot Spots ---
cam03:LWrist   18.2%
cam01:LElbow   15.7%
cam03:LElbow   14.3%
...

--- Threshold Simulation ---
Threshold   Excluded frames (additional)
0.4 → 0.5  cam01: +3.2%, cam02: +1.8%, cam03: +5.1%, cam04: +0.9%
0.4 → 0.6  cam01: +8.3%, cam02: +4.2%, cam03: +11.5%, cam04: +2.1%
```
