# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## このリポジトリでの役割

このリポジトリはPose2Simライブラリ本体（マーカーレス3D運動解析）だが、**ユーザー（sakagawa）はPose2Simの利用者・データ解析者**であり、ライブラリ開発者ではない。Claude Codeの主な目的は、Pose2Simが生成した3Dキーポイントデータの解析・処理を支援すること。

## インストール・セットアップ

```bash
pip install -e .      # 開発モード（ローカル変更を即反映）
pip install pose2sim  # 通常インストール
```

テスト実行:
```bash
tests_pose2sim
```

## データの場所と形式

### 実測データセット（`Pose2Sim/` 以下）

| ディレクトリ | 内容 |
|---|---|
| `20251024_osaka-hosp.1min/` | 大阪病院、1分間、複数カメラ |
| `20251024_osaka-hosp.1min.3cam/` | 大阪病院、1分間、3カメラ限定 |
| `20251024_osaka-hosp.Calib_PortalCam.10min/` | 大阪病院、PortalCam、10分 |
| `20251024_osaka-hosp.1hour/` | 大阪病院、1時間 |
| `20251113_dgtw-lab2/` | dgtw-lab2実験室（11月13日） |
| `20251114_dgtw-lab2/` | dgtw-lab2実験室（11月14日） |
| `20251121_dgtw-lab2/` | dgtw-lab2実験室（11月21日） |
| `20251127-dgtw-lab2/` | dgtw-lab2実験室（11月27日） |
| `20260227-dgtw2-lab2/` | dgtw-lab2実験室（2月27日、設定変更版） |

各セッションのディレクトリ構造:
```
{session}/
├── Config.toml          # 処理設定
├── calibration/         # カメラキャリブレーション
├── videos/              # 入力動画
├── pose/                # 2D姿勢推定結果（OpenPose JSON）
├── pose-sync/           # 同期後の2D姿勢
├── pose-associated/     # 人物関連付け後
└── pose-3d/             # 3D三角測量結果（.trcファイル）★主な解析対象
```

### TRCファイルの命名規則

```
{session_name}_{start_frame}-{end_frame}.trc                      # 生の三角測量結果
{session_name}_{start_frame}-{end_frame}_filt_butterworth.trc     # Butterworthフィルタ後
{session_name}_{start_frame}-{end_frame}_filt_butterworth_LSTM.trc  # フィルタ後＋マーカー拡張 ★推奨
```

### TRCファイルの形式

タブ区切りテキスト（単位: メートル）:
```
行1: PathFileType  4  (X/Y/Z)  {filename}
行2: DataRate  CameraRate  NumFrames  NumMarkers  Units  OrigDataRate  ...
行3: {fps}  {fps}  {nframes}  {nmarkers}  m  ...
行4: Frame#  Time  {marker1}     {marker2}  ...   （マーカー名、3列おき）
行5: (空)  (空)  X1  Y1  Z1  X2  Y2  Z2  ...
行6+: {frame}  {time}  {x}  {y}  {z}  ...
```

### LSTMマーカー拡張ファイルのマーカー構成（69マーカー）

最初の26個（HALPE_26 姿勢推定キーポイント）:
`Hip, RHip, RKnee, RAnkle, RBigToe, RSmallToe, RHeel, LHip, LKnee, LAnkle, LBigToe, LSmallToe, LHeel, Neck, Head, Nose, LEye, REye, LEar, REar, RShoulder, RElbow, RWrist, LShoulder, LElbow, LWrist`

残り43個（LSTMで推定した仮想マーカー、`_study` サフィックス）:
`r.ASIS_study, L.ASIS_study, r.PSIS_study, L.PSIS_study, r_knee_study, r_mknee_study, r_ankle_study ...`（OpenSim解析用）

Pythonでの読み込み例:
```python
import pandas as pd
df = pd.read_csv('path/to/file.trc', sep='\t', skiprows=4, header=[0, 1])
# または
df = pd.read_csv('path/to/file.trc', sep='\t', skiprows=5)
```

## TRC操作ユーティリティ（CLIコマンド）

```bash
trc_plot -i file.trc                          # 可視化
trc_filter -i file.trc -f butterworth         # フィルタリング
trc_scale -i file.trc -s 0.001               # スケール変換（mm→m）
trc_rotate -i file.trc -ax X -a 90          # 座標回転
trc_desample -i file.trc -fr 60 -f 30       # ダウンサンプリング
trc_combine -i file1.trc file2.trc           # 複数TRCの結合
trc_gaitevents -i file.trc                   # 歩行イベント検出
trc_Zup_to_Yup -i file.trc                  # 座標系変換（Z-up→Y-up）
trc_to_c3d -i file.trc                       # C3D形式に変換
c3d_to_trc -i file.c3d                       # TRC形式に変換
```

## アーキテクチャ概要

Pose2Simの処理パイプライン（各ステップは独立して呼び出し可能）:

```
calibration() → poseEstimation() → synchronization() → personAssociation()
→ triangulation() → filtering() → markerAugmentation() → kinematics()
```

- `Pose2Sim/Pose2Sim.py`: エントリーポイント、設定読み込み、ステップ制御
- `Pose2Sim/common.py`: TRC読み書きなど共通ユーティリティ（55KB）
- `Pose2Sim/skeletons.py`: anytreeベースの骨格階層定義（各姿勢モデルのキーポイント接続）
- `Pose2Sim/Utilities/`: 独立したCLIスクリプト群（TRC操作、形式変換など）
- `Pose2Sim/OpenSim_Setup/`: OpenSimモデルファイル（.osim, .xml）
- `Pose2Sim/MarkerAugmenter/`: LSTMモデルと関連コード

設定は `Config.toml` で管理。Session > Participant > Trial の階層構造をサポートし、上位の設定を下位が継承・上書きできる。

## Python環境

```bash
micromamba activate Pose2Sim
```
Bashツールから使う場合は以下を先頭に付ける:
```bash
export MAMBA_EXE='/home/sakagawa/.micromamba/bin/micromamba' && export MAMBA_ROOT_PREFIX='/home/sakagawa/micromamba' && eval "$("$MAMBA_EXE" shell hook --shell bash --root-prefix "$MAMBA_ROOT_PREFIX" 2>/dev/null)" && micromamba activate Pose2Sim && <コマンド>
```

## 作業ルール

### 基本フロー

各改善ステップは以下の流れで進める:

1. **調査→計画**: planモードを使用。コードベース調査・方針策定を行い、ユーザーに計画を提示する
2. **承認**: ユーザーが計画を確認・承認する
3. **ドキュメント更新（必須）**: 承認直後、実行前に必ず以下を更新する:
   - `docs/{管理番号}_{名称}/README.md` に調査結果・計画内容を記録
   - `docs/accuracy_improvement_plan.md` のステップ一覧・変更履歴を更新
   - `CLAUDE.md` に新たな知見があれば追記
4. **実行**: 承認された計画に基づいて実施する

### 実行時のルール

- **テスト（Pose2Simの処理実行、精度評価、パラメータ比較など）はsubagent（Taskツール）を使って実行する。** メインの会話コンテキストを消費せず、並列実行も可能にするため。

### 管理ドキュメント

- 改善計画: `docs/accuracy_improvement_plan.md`
- 各ステップ詳細: `docs/{管理番号}_{名称}/README.md`

### セッション開始時

`/clear`や新規セッション開始時は、まず `docs/accuracy_improvement_plan.md` を読んで現在の進捗を把握すること。

## 三角測量の既知の問題と対策（2026-02-27調査済み）

### handle_LR_swap=true による左右キーポイント重なり問題

**対象データ**: `20251127-dgtw-lab2` / `20260227-dgtw2-lab2`（同一データ、後者は設定変更版）

**症状**: 3D三角測量結果で右腕と左腕がほぼ同一座標に重なる（肩距離0.007m等）。肩39%、肘71%、手首76%のフレームで発生。

**原因**: `handle_LR_swap = true` のスワップアルゴリズムが、一部カメラのL/Rラベルを誤って入れ替え、左右の中間点に収束させていた。2Dポーズデータ自体にはL/R混同なし（各カメラで80〜145px分離）。

**対策**: `Config.toml` で `handle_LR_swap = false` に設定。修正後は全フレームでL/R重なり0件、急反転も0件。

### undistort_points=true での再投影誤差増加（002で部分改善済み）

**症状**: `undistort_points = true` にすると再投影誤差が増加（9.9px→11.4px）、カメラ除外率が倍増（0.48→0.96台）。cam01/cam03の除外率が35-38%に。

**原因**: cam01/cam03の望遠レンズの歪みモデル精度が不十分。

**002で実施した対策**: `CALIB_FIX_K3` を除去してk3パラメータを解放→5パラメータモデルで再キャリブレーション。

**結果**: 再投影誤差・カメラ除外率は改善しなかったが、**TRC品質は全指標で改善**:
- Bone CV: 18.0% → 16.4%
- Smoothness: 0.0189 → 0.0139 (-26%)
- L-R Diff: 6.3% → 4.9%

**現在の推奨**: `undistort_points = true` を使用。カメラ除外が増えても残ったカメラでの三角測量の質が向上するため。

**案B/Cの結果**: 案B（alpha=0）はcam除外率改善だがSmooth/L-R悪化で不採用。案C（画像品質フィルタ）はcam01のみ13枚除外で効果限定的、不採用。案A設定を維持。コードは`calibration.py`に残置（害なし）。

### カメラ構成メモ（20251127-dgtw-lab2）

- 4台カメラ: cam01〜cam04（すべて1920x1080）
- cam01/cam03: 焦点距離長い（f≈2015,2040）、レンズ歪み大（k1≈-0.15）
- cam02/cam04: 焦点距離短い（f≈1186,1178）、レンズ歪み小（k1≈-0.03）
- カメラ間距離: 1.5〜3.1m

### 推奨Config.toml設定（20251127-dgtw-lab2系）

```toml
[triangulation]
handle_LR_swap = false           # 必須: trueだとL/R重なり発生
undistort_points = true          # k3解放後はtrue推奨（BoneCV/Smooth/L-R全改善）
reproj_error_threshold_triangulation = 15.0  # 現状維持
likelihood_threshold_triangulation = 0.4     # 精度向上には0.5も検討可
min_cameras_for_triangulation = 2            # 精度向上には3も検討可
fill_large_gaps_with = "last_value"          # "nan"も検討可
make_c3d = true                  # C3D変換（バグ修正済みで動作する）

[filtering]
display_figures = false          # バッチ実行時はfalse推奨
save_filt_plots = true           # フィルタプロットを保存
make_c3d = true                  # フィルタ後のC3D生成（必須: 明示しないとNone=無効）

[logging]
use_custom_logging = false       # save_logs/levelは未実装。これだけが有効
```

### ログファイルの注意点

Pose2Simのログは**セッションの親ディレクトリ**に書き込まれる（level=1の場合）。各trialディレクトリ内の`logs.txt`は古い場合がある。最新ログは `/home/sakagawa/git/pose2sim/Pose2Sim/logs.txt` を確認すること。

**Config.tomlの`[logging]`セクション**: `save_logs` と `level` はPose2Simコードで**未実装**（無視される）。唯一認識されるのは `use_custom_logging`（デフォルトfalse）。

### intrinsicsキャリブレーション実装の設計制約（2026-02-28調査済み）

**ファイル**: `Pose2Sim/calibration.py`

3つの制約を特定し、すべて対処済み:
1. ~~**歪みモデル4パラメータ制限**（行789）~~ → **案A完了・採用**: `CALIB_FIX_K3`除去済み、5パラメータモデルに変更。TRC品質改善
2. ~~**alpha=1問題**（`common.py:281`）~~ → **案B完了・不採用**: alpha=0でcam除外率改善するがSmooth/L-R悪化
3. ~~**画像品質フィルタなし**~~ → **案C完了・不採用**: 画像品質フィルタ実装済みだが効果限定的（cam01のみ13枚除外）

**結論**: キャリブレーション側の改善は案Aのk3解放のみ有効。cam01/cam03の除外率35-39%はキャリブレーションでは解決困難。

### triangulation()のC3D変換バグ（2026-02-28修正済み）

**ファイル**: `Pose2Sim/triangulation.py` 行929
**症状**: `make_c3d = true` にしてもtriangulation()後にC3Dファイルが生成されない。ログには「All trc files have been converted to c3d.」と出力されるが虚偽。
**原因**: `c3d_paths.append(convert_to_c3d(t) for t in trc_paths)` がジェネレータ式をappendしており、`convert_to_c3d()`が実行されない。
**修正**: `c3d_paths.append(convert_to_c3d(trc_paths[-1]))` に変更（ローカル修正済み）。
**回避策**: filtering()の `[filtering]` セクションに `make_c3d = true` を設定すればC3D生成可（filtering.pyのコードは正しい）。
