# 009: 定量的精度評価基盤の構築 [計画済み・実装待ち]

## 1. なぜ必要か

現在の問題を一言でいうと：**「改善したかどうか」を数値で判断できない**。

### 具体的な問題

- ステップ001で `handle_LR_swap=false` にした → 「L/R重なりが消えた」のは目視で確認できた
- しかし、これから取り組むステップ002〜008では効果がもっと微妙になる
  - キャリブレーション改善 → 再投影誤差が 11.4px → 何px になれば「改善」？
  - `likelihood_threshold` を 0.4 → 0.5 に変更 → 精度は上がる？データ欠損は増える？トレードオフは？
  - フィルタのカットオフ周波数 6Hz → 8Hz → 動きの忠実性は？ノイズは？

**目視で判断するのは限界がある。** 1770フレーム × 26マーカー = 45,000以上のデータポイントを人間が見て「良くなった」と言っても信頼性がない。

**設定を変えるたびに自動で数値を出して比較できる仕組み**が先に必要。

## 2. 評価指標（何を測るか）

このデータセットには**光学マーカーなどのグラウンドトゥルース（正解データ）がない**。そのため、「絶対的な精度」ではなく**物理的・解剖学的に正しいか**を内部整合性で評価する。

### 指標A: 骨長の一貫性（最重要）

```
人体の骨の長さは時間とともに変わらない
→ 各フレームで「肩→肘」の距離を計算し、全フレームで一定かを見る
```

- **計算**: `bone_length = ||marker_A - marker_B||` を全フレームで計算
- **評価値**: 標準偏差（SD）と変動係数（CV = SD/平均）
- **例**: 上腕（RShoulder→RElbow）が平均0.28m、SD=0.005m → CV=1.8%（良好）
  - SD=0.03m → CV=10.7%（不良、三角測量にブレがある）

**なぜこの指標か**:
- グラウンドトゥルース不要で計算できる
- 物理的に「骨の長さは変わらない」という不変量に基づくため根拠が明確
- 三角測量のブレ、カメラキャリブレーションの精度が直接反映される

### 指標B: 軌跡の滑らかさ（ジッター検出）

```
人体は急に瞬間移動しない
→ 各マーカーの加速度を計算し、異常な急変動を検出する
```

- **計算**: 2次差分（加速度）の大きさ `|pos[t+1] - 2*pos[t] + pos[t-1]|`
- **評価値**: 加速度の中央値、95パーセンタイル（単位: m/frame²）
- **例**: 95パーセンタイルが 0.01m/frame² → 滑らか（良好）
  - 0.05m/frame² → ガタガタ（不良）

**なぜこの指標か**:
- フィルタリングの効果を直接測定できる（ステップ008の評価に必須）
- 三角測量の「飛び」（1フレームだけ座標が大きくずれる）を検出

### 指標C: 欠損データ分析

```
信頼度の閾値を上げると精度は上がるがデータが欠損する
→ 各マーカーのNaN率（欠損率）を記録する
```

- **計算**: 各マーカーの `NaN / 全フレーム数 × 100%`
- **評価値**: マーカーごとのNaN率、全体のNaN率

**なぜこの指標か**:
- ステップ004（likelihood_threshold）、005（min_cameras）のトレードオフ評価に必須
- 「精度は上がったがデータの半分が欠損した」では使い物にならない

### 指標D: 左右対称性

```
左右の対応する骨の長さは本来ほぼ等しい
→ 左上腕と右上腕の長さの差を見る
```

- **計算**: `|mean(L_bone) - mean(R_bone)| / mean(L_bone, R_bone) × 100%`
- **評価値**: 左右差（%）

**なぜこの指標か**:
- ステップ001で修正したL/R重なり問題の再発検出
- カメラ配置の偏りによる左右精度差の可視化

## 3. 実現手段（何を作るか）

**1つのPythonスクリプト**を作る。TRCファイルを渡すと全指標を自動計算してレポートを出力する。

### 配置場所

`Pose2Sim/Utilities/trc_evaluate.py`

**選定理由**:
- 既存の `trc_plot.py`, `trc_filter.py`, `trc_gaitevents.py` 等と同じディレクトリで、`trc_*` の命名規則に合致する
- CLIエントリーポイント（`trc_evaluate` コマンド）として `pyproject.toml` に登録できる
- 同パッケージ内なので `from Pose2Sim.common import extract_trc_data` でTRC読み込み関数をインポート可能

### なぜこの手段を選んだか

| 選択肢 | 却下理由 |
|--------|---------|
| Jupyter Notebook | 毎回手動でセルを実行する必要がある。設定を変えるたびに面倒 |
| 目視（trc_plotコマンド） | 1770フレーム×26マーカーを人間が見て判断するのは非現実的 |
| 外部ツール（OpenSimなど） | 環境構築が重い。評価だけのためにはオーバースペック |
| **CLIスクリプト** | **採用**: コマンド1発で結果が出る。パイプラインに組み込みやすい。Pose2Simの`common.py`のTRC読み込み関数をそのまま使える |

## 4. 実装設計（調査・計画完了済み）

### 4.1 変更対象ファイル

| ファイル | 操作 |
|---------|------|
| `Pose2Sim/Utilities/trc_evaluate.py` | **新規作成** |
| `pyproject.toml` 行93付近 | エントリーポイント1行追加 |

### 4.2 モジュール構造

```
main()                           # argparse CLI
trc_evaluate_func(**args)        # オーケストレータ
  ├── load_trc_as_marker_dict()  # TRC読み込み → {マーカー名: (n_frames,3)} dict
  ├── evaluate_single()          # 4指標をまとめて計算
  │   ├── compute_bone_lengths()   # 指標A: 骨長の一貫性
  │   ├── compute_smoothness()     # 指標B: 軌跡の滑らかさ
  │   ├── compute_missing_data()   # 指標C: 欠損データ
  │   └── compute_symmetry()       # 指標D: 左右対称性
  ├── format_report()            # 単体レポート（ターミナル出力）
  ├── format_comparison_report() # 比較レポート（ターミナル出力）
  ├── save_csv()                 # 単体CSV保存
  └── save_comparison_csv()      # 比較CSV保存
```

既存パターンに合わせた `main()` → `trc_evaluate_func(**args)` の2層構造。

#### 各関数の入出力型仕様

```python
def load_trc_as_marker_dict(trc_path: str) -> tuple:
    """TRCファイルを読み込み、マーカーごとの3D座標辞書に変換する。

    Returns:
        marker_names: list[str]           # マーカー名一覧（例: ['Hip', 'RHip', ...]）
        time_arr:     np.ndarray          # shape (n_frames,) 時間（秒）
        markers_3d:   dict[str, ndarray]  # {マーカー名: shape (n_frames, 3) のXYZ座標}
        fps:          float               # フレームレート
    """

def compute_bone_lengths(
    markers_3d: dict[str, ndarray],
    bones: list[tuple[str,str,str]] = HALPE_26_BONES
) -> list[dict]:
    """各骨の長さを全フレームで計算し、統計量を返す。

    Returns: list of dict, 各要素:
        {'name': str,           # 骨の表示名（例: 'R Thigh'）
         'parent': str,         # 親マーカー名
         'child': str,          # 子マーカー名
         'mean': float,         # 平均長（m）
         'sd': float,           # 標準偏差（m）
         'cv': float,           # 変動係数（%）
         'n_valid': int}        # 有効フレーム数（NaN除外後）
    """

def compute_smoothness(
    markers_3d: dict[str, ndarray],
    marker_names: list[str],
    fps: float
) -> list[dict]:
    """各マーカーの加速度（2次差分）を計算し、統計量を返す。

    Returns: list of dict, 各要素:
        {'name': str,              # マーカー名
         'accel_median': float,    # 加速度の中央値（m/frame²）
         'accel_p95': float,       # 加速度の95パーセンタイル（m/frame²）
         'accel_median_si': float, # 中央値をSI単位に変換（m/s²、= median × fps²）
         'accel_p95_si': float,    # 95%ileをSI単位に変換（m/s²）
         'n_valid': int}           # 有効フレーム数
    """

def compute_missing_data(
    markers_3d: dict[str, ndarray],
    marker_names: list[str]
) -> list[dict]:
    """各マーカーのNaN率を計算する。

    Returns: list of dict, 各要素:
        {'name': str,           # マーカー名
         'n_total': int,        # 全フレーム数
         'n_missing': int,      # NaNフレーム数
         'missing_pct': float}  # NaN率（%）
    """

def compute_symmetry(
    bone_results: list[dict],
    symmetric_pairs: list[tuple[str,str,str]] = SYMMETRIC_BONE_PAIRS
) -> list[dict]:
    """左右対称骨ペアの平均長を比較する。

    Args:
        bone_results: compute_bone_lengths() の戻り値

    Returns: list of dict, 各要素:
        {'pair_name': str,      # ペア表示名（例: 'Thigh'）
         'left_name': str,      # 左骨の表示名
         'right_name': str,     # 右骨の表示名
         'left_mean': float,    # 左骨の平均長（m）
         'right_mean': float,   # 右骨の平均長（m）
         'diff_pct': float}     # 差（%）
    """

def evaluate_single(trc_path: str) -> dict:
    """1つのTRCファイルに対し全4指標を計算する。

    Returns: dict
        {'trc_path': str,
         'n_frames': int,
         'n_markers': int,
         'fps': float,
         'bone_results': list[dict],      # compute_bone_lengths() の戻り値
         'smooth_results': list[dict],     # compute_smoothness() の戻り値
         'missing_results': list[dict],    # compute_missing_data() の戻り値
         'symmetry_results': list[dict],   # compute_symmetry() の戻り値
         'summary': {                      # 全体サマリ
             'mean_cv': float,             # 骨長CVの平均（%）
             'worst_bone': str,            # 最悪CV値の骨名
             'worst_cv': float,            # 最悪CV値（%）
             'mean_accel_p95': float,      # 加速度95%ileの平均（m/frame²）
             'overall_nan_pct': float,     # 全体NaN率（%）
             'mean_lr_diff': float}}       # 左右差の平均（%）
    """

def format_report(eval_result: dict) -> str:
    """単体評価結果をターミナル表示用テキストに整形する。"""

def format_comparison_report(eval_a: dict, eval_b: dict) -> str:
    """2ファイルの評価結果を比較テキストに整形する。"""

def save_csv(eval_result: dict, csv_path: str) -> None:
    """単体評価結果をCSVファイルに保存する。"""

def save_comparison_csv(eval_a: dict, eval_b: dict, csv_path: str) -> None:
    """比較結果をCSVファイルに保存する。"""

def trc_evaluate_func(**args) -> Union[dict, tuple[dict, dict]]:
    """オーケストレータ。入力ファイル数に応じて単体/比較モードを実行する。

    Args:
        input: list[str]    # TRCファイルパスのリスト（1つまたは2つ）
        output: str | None  # 出力CSVパス（Noneなら自動命名）

    Returns:
        単体モード: dict（evaluate_single()の戻り値）
        比較モード: tuple[dict, dict]（2つのevaluate_single()の戻り値）
    """
```

### 4.3 骨の接続定義（20本）

HALPE_26の親子関係（`skeletons.py`行50-90）に基づく。頭部の細かい接続（Nose, Eye, Ear）は距離が小さすぎてノイズに支配されるため除外。

```python
HALPE_26_BONES = [
    # 右脚
    ('Hip',       'RHip',      'Hip-RHip'),
    ('RHip',      'RKnee',     'R Thigh'),
    ('RKnee',     'RAnkle',    'R Shank'),
    ('RAnkle',    'RBigToe',   'R Foot'),
    ('RBigToe',   'RSmallToe', 'R Toe'),
    ('RAnkle',    'RHeel',     'R Heel'),
    # 左脚
    ('Hip',       'LHip',      'Hip-LHip'),
    ('LHip',      'LKnee',     'L Thigh'),
    ('LKnee',     'LAnkle',    'L Shank'),
    ('LAnkle',    'LBigToe',   'L Foot'),
    ('LBigToe',   'LSmallToe', 'L Toe'),
    ('LAnkle',    'LHeel',     'L Heel'),
    # 体幹
    ('Hip',       'Neck',      'Trunk'),
    ('Neck',      'Head',      'Neck-Head'),
    # 右腕
    ('Neck',      'RShoulder', 'Neck-RShoulder'),
    ('RShoulder', 'RElbow',    'R Upper Arm'),
    ('RElbow',    'RWrist',    'R Forearm'),
    # 左腕
    ('Neck',      'LShoulder', 'Neck-LShoulder'),
    ('LShoulder', 'LElbow',    'L Upper Arm'),
    ('LElbow',    'LWrist',    'L Forearm'),
]
```

### 4.4 左右対称ペア（9組）

```python
SYMMETRIC_BONE_PAIRS = [
    ('Hip-LHip',      'Hip-RHip',      'Hip'),
    ('L Thigh',       'R Thigh',       'Thigh'),
    ('L Shank',       'R Shank',       'Shank'),
    ('L Foot',        'R Foot',        'Foot'),
    ('L Toe',         'R Toe',         'Toe'),
    ('L Heel',        'R Heel',        'Heel'),
    ('Neck-LShoulder','Neck-RShoulder','Shoulder'),
    ('L Upper Arm',   'R Upper Arm',   'Upper Arm'),
    ('L Forearm',     'R Forearm',     'Forearm'),
]
```

### 4.5 データ読み込み方法

`Pose2Sim/common.py:178` の `extract_trc_data()` を使用:

```python
from Pose2Sim.common import extract_trc_data

marker_names, trc_data_np = extract_trc_data(trc_path)
# trc_data_np shape: (n_frames, 1 + 3*n_markers)
# 列0 = time, 列1-3 = marker0のXYZ, 列4-6 = marker1のXYZ, ...

time_arr = trc_data_np[:, 0]
coords = trc_data_np[:, 1:]
coords_3d = coords.reshape(n_frames, n_markers, 3)
markers_3d = {name: coords_3d[:, i, :] for i, name in enumerate(marker_names)}
```

FPSはTRCヘッダー3行目（`lines[2].split('\t')[0]`）から取得。

### 4.6 各指標の計算ロジック

**A. 骨長の一貫性**:
- `bone_length[t] = ||child[t] - parent[t]||` を全フレームで計算
- NaN処理: どちらかのマーカーがNaN → normもNaN → `nanmean`/`nanstd`で自動除外
- 長さ0は NaN に置換（両マーカー欠損のケース防止）
- 出力: mean, SD, CV(=SD/mean×100%)

**B. 軌跡の滑らかさ**:
- `accel[t] = pos[t+1] - 2*pos[t] + pos[t-1]`（2次差分）
- `accel_mag = ||accel||`
- NaN処理: NaN座標があるフレームは自動的にNaN → 除外
- 出力: median, 95パーセンタイル（単位: m/frame²）

**C. 欠損データ**:
- X,Y,Zのいずれかが NaN → そのフレームは欠損
- 出力: マーカーごとのNaN率(%)、全体NaN率

**D. 左右対称性**:
- 骨長結果（指標A）の左右対応ペアの平均長を比較
- `diff_pct = |L_mean - R_mean| / avg(L_mean, R_mean) × 100%`

### 4.7 CLI引数

```python
parser.add_argument('-i', '--input', required=True, nargs='+',
                    help='1つ: 単体評価、2つ: 比較モード')
parser.add_argument('-o', '--output', required=False, default=None,
                    help='出力CSVパス（省略時は自動命名）')
```

#### CSV自動命名ルール（`-o` 省略時）

| モード | 生成ファイル名 | 例 |
|--------|-------------|-----|
| 単体 | `{入力ファイルstem}_evaluation.csv` | `20260227-dgtw2-lab2_1-1770_evaluation.csv` |
| 比較 | `{ファイルA stem}_vs_{ファイルB stem}_comparison.csv` | `20251127-dgtw-lab2_1-1770_vs_20260227-dgtw2-lab2_1-1770_comparison.csv` |

出力先は入力ファイルと同じディレクトリ。

### 4.8 出力フォーマット

#### ターミナル（単体評価）

```
=== TRC Evaluation Report ===
File: xxx.trc | Frames: 1770 | Markers: 26 | FPS: 30.0

--- A. Bone Length Consistency ---
                      Mean(m)   SD(m)   CV(%)
  R Thigh              0.412   0.005    1.2%
  ...
  Summary: Mean CV = 4.1%

--- B. Trajectory Smoothness (m/frame^2) ---
                    Median    95%ile
  Hip               0.0008    0.0031
  ...

--- C. Missing Data ---
                    NaN Rate
  Hip                 0.0%
  ...
  Summary: Overall = 1.2%

--- D. Left-Right Symmetry ---
                    L(m)     R(m)     Diff(%)
  Thigh             0.413    0.412     0.2%
  ...

=== Summary ===
  Bone CV: 4.1%  |  Smoothness 95%ile: 0.0082  |  NaN: 1.2%  |  L-R Diff: 1.1%
```

#### ターミナル（比較モード）

```
================================================================================
TRC Comparison Report
File A (before): 20251127-dgtw-lab2_1-1770.trc
File B (after):  20260227-dgtw2-lab2_1-1770.trc
================================================================================

--- A. Bone Length Consistency (CV%) ---
                      Before   After    Change
  Hip-RHip              5.2%    3.1%    -2.1%  IMPROVED
  R Thigh               2.4%    1.2%    -1.2%  IMPROVED
  R Shank               3.1%    1.8%    -1.3%  IMPROVED
  ...
  Summary: Mean CV    3.8% ->  2.5%    -1.3%  IMPROVED

--- B. Trajectory Smoothness (95%ile, m/frame^2) ---
                      Before    After    Change
  Hip                 0.0035    0.0031   -11.4%  IMPROVED
  RHip                0.0040    0.0035   -12.5%  IMPROVED
  ...
  Summary: Mean 95%ile  0.0100 -> 0.0082  -18.0%  IMPROVED

--- C. Missing Data (NaN%) ---
                      Before   After    Change
  Hip                   0.0%     0.0%     0.0%
  RWrist                1.8%     3.2%    +1.4%  WORSE
  ...
  Summary: Overall    1.0% ->  1.2%    +0.2%  WORSE

--- D. Left-Right Symmetry (Diff%) ---
                      Before   After    Change
  Hip                   8.5%     1.0%    -7.5%  IMPROVED
  Thigh                 5.2%     0.2%    -5.0%  IMPROVED
  ...
  Summary: Mean Diff  4.3% ->  1.1%    -3.2%  IMPROVED

================================================================================
Overall Summary
                      Before          After
  Bone CV (mean):      3.8%            2.5%   IMPROVED
  Smooth 95%ile:       0.0100          0.0082 IMPROVED
  NaN rate:            1.0%            1.2%   WORSE
  L-R Diff (mean):     4.3%            1.1%   IMPROVED
================================================================================
```

判定基準: 値が減少 → IMPROVED、増加 → WORSE、変化なし → 表示なし。

#### CSV（単体）

`metric,item,value,unit,detail` の5列形式。

```csv
metric,item,value,unit,detail
bone_cv,Hip-RHip,3.1,%,mean=0.0960 sd=0.0030
bone_cv,R Thigh,1.2,%,mean=0.4120 sd=0.0050
bone_cv,R Shank,1.8,%,mean=0.3980 sd=0.0070
smoothness_p95,Hip,0.0031,m/frame^2,median=0.0008
smoothness_p95,RHip,0.0035,m/frame^2,median=0.0009
missing,Hip,0.0,%,0/1770
missing,RWrist,3.2,%,57/1770
symmetry,Hip,1.0,%,L=0.0950 R=0.0960
symmetry,Thigh,0.2,%,L=0.4130 R=0.4120
summary,bone_cv_mean,4.1,%,
summary,smoothness_p95_mean,0.0082,m/frame^2,
summary,missing_overall,1.2,%,
summary,symmetry_mean,1.1,%,
```

#### CSV（比較）

`metric,item,before,after,change,unit,verdict` の7列形式。

```csv
metric,item,before,after,change,unit,verdict
bone_cv,Hip-RHip,5.2,3.1,-2.1,%,IMPROVED
bone_cv,R Thigh,2.4,1.2,-1.2,%,IMPROVED
smoothness_p95,Hip,0.0035,0.0031,-0.0004,m/frame^2,IMPROVED
missing,RWrist,1.8,3.2,+1.4,%,WORSE
symmetry,Hip,8.5,1.0,-7.5,%,IMPROVED
summary,bone_cv_mean,3.8,2.5,-1.3,%,IMPROVED
summary,smoothness_p95_mean,0.0100,0.0082,-0.0018,m/frame^2,IMPROVED
summary,missing_overall,1.0,1.2,+0.2,%,WORSE
summary,symmetry_mean,4.3,1.1,-3.2,%,IMPROVED
```

### 4.9 `pyproject.toml` への追加

行93（`trc_scale` の後）に以下を追加:
```toml
trc_evaluate = "Pose2Sim.Utilities.trc_evaluate:main"
```

### 4.10 依存関係

- `numpy`（既存依存）のみ。追加パッケージ不要
- 内部: `from Pose2Sim.common import extract_trc_data`

### 4.11 エッジケース対応

| ケース | 対処 |
|--------|------|
| LSTM拡張TRC（69マーカー） | 骨定義にないマーカーは骨長・対称性の評価からはスキップ。滑らかさ・欠損は全マーカー評価 |
| TRCにないマーカーが骨定義に含まれる | `compute_bone_lengths` でスキップ |
| 全フレームNaNのマーカー | 各指標でNaN結果を返す |
| 3フレーム未満のTRC | 滑らかさ（2次差分）はNaN結果を返す |

## 5. 実装手順

| # | やること | 規模 |
|---|---------|------|
| 1 | `Pose2Sim/Utilities/trc_evaluate.py` を新規作成（全関数を含む） | 中 |
| 2 | `pyproject.toml` にエントリーポイント追加 | 小 |
| 3 | `pip install -e .` で再インストール | 小 |
| 4 | 単体モードでテスト: `trc_evaluate -i .../20260227-dgtw2-lab2_1-1770.trc` | 小 |
| 5 | 比較モードでテスト: `trc_evaluate -i .../20251127...trc .../20260227...trc` | 小 |
| 6 | LSTM拡張TRC（69マーカー）でもエラーなく動作することを確認 | 小 |
| 7 | ベースライン結果をこのREADMEのセクション7に記録 | 小 |

## 6. 対象データ

- 主な評価対象: `Pose2Sim/20260227-dgtw2-lab2/pose-3d/`
- フレーム数: 1770（約59秒、30fps）
- マーカー数: 26個（HALPE_26）/ LSTM版は69個
- 座標系: Y-up、単位メートル

### TRCファイル一覧

| ファイル | 内容 |
|---------|------|
| `20260227-dgtw2-lab2_1-1770.trc` | 生の三角測量結果（handle_LR_swap=false版） |
| `20260227-dgtw2-lab2_1-1771_filt_butterworth.trc` | Butterworthフィルタ後 |
| `20251127-dgtw-lab2_1-1770.trc` | 旧設定（参考比較用） |
| `20251127-dgtw-lab2_1-1771_filt_butterworth.trc` | 旧設定フィルタ後 |
| `20251127-dgtw-lab2_1-1771_filt_butterworth_LSTM.trc` | 旧設定 + LSTM拡張（69マーカー） |

## 7. 成功基準

- 改善の前後比較が定量的にできる状態
- コマンド1つでレポートが出力される
- CSV出力により、複数回の比較結果を蓄積・追跡できる

## 8. ベースライン計測結果

### 計測日: 2026-02-28

#### 8.1 単体評価: 20260227-dgtw2-lab2_1-1770.trc（handle_LR_swap=false、フィルタなし）

| 指標 | 値 |
|------|-----|
| Bone CV (mean) | 20.2% |
| Smoothness 95%ile (mean) | 0.1033 m/frame² |
| NaN rate | 0.0% |
| L-R Diff (mean) | 6.1% |

骨長CV上位（最も不安定な部位）:
| 骨 | CV(%) | 平均長(m) | SD(m) |
|----|-------|-----------|-------|
| L Toe | 62.7% | 0.0640 | 0.0401 |
| R Toe | 53.5% | 0.0695 | 0.0372 |
| L Heel | 36.2% | 0.0676 | 0.0245 |
| R Heel | 35.2% | 0.0732 | 0.0257 |
| L Forearm | 32.0% | 0.2593 | 0.0829 |

加速度95%ile上位（最もジッターが大きい部位）:
| マーカー | 95%ile (m/frame²) |
|----------|-------------------|
| LWrist | 0.3029 |
| LElbow | 0.2513 |
| REye | 0.1636 |
| LEar | 0.1559 |
| LBigToe | 0.1371 |

#### 8.2 比較: 旧設定 vs 新設定（handle_LR_swap=true → false）

| 指標 | Before (旧) | After (新) | 変化 | 判定 |
|------|------------|-----------|------|------|
| Bone CV (mean) | 35.9% | 20.2% | -15.7% | IMPROVED |
| Smoothness 95%ile (mean) | 0.2571 | 0.1033 | -59.8% | IMPROVED |
| NaN rate | 0.0% | 0.0% | 0.0% | — |
| L-R Diff (mean) | 8.6% | 6.1% | -2.5% | IMPROVED |

**主な改善**: handle_LR_swap=false により骨長CVが約44%改善（35.9→20.2）、滑らかさが約60%改善。特に右腕系（RShoulder, RElbow）の加速度が85-87%改善。

#### 8.3 LSTM拡張TRC: 20251127-dgtw-lab2_1-1771_filt_butterworth_LSTM.trc（69マーカー）

| 指標 | 値 |
|------|-----|
| Bone CV (mean) | 33.6% |
| Smoothness 95%ile (mean) | 0.0280 m/frame² |
| NaN rate | 0.0% |
| L-R Diff (mean) | 8.6% |

**注**: これは旧設定（handle_LR_swap=true）+ Butterworthフィルタ + LSTM拡張の結果。滑らかさはフィルタ効果で大幅に良いが（0.0280 vs 0.1033）、骨長CVは旧設定ベースのため高い（33.6%）。69マーカー中、HALPE_26の20本の骨のみ骨長評価の対象。_studyマーカーは滑らかさ・欠損のみ評価。

#### 8.4 今後の比較用リファレンス値

新設定（handle_LR_swap=false）のフィルタなし結果をベースラインとする:

```
Bone CV:    20.2%
Smooth:     0.1033 m/frame²
NaN:        0.0%
L-R Diff:   6.1%
```

ステップ002以降の各改善で、これらの値がどう変化するかを追跡する。
