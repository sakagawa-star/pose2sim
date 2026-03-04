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

## 自作CLIツール（本プロジェクトで追加）

```bash
trc_evaluate -i file.trc                      # TRC品質評価（BoneCV/Smoothness/NaN率/L-R対称性）
trc_evaluate -i before.trc after.trc          # 2ファイル比較モード
pose_confidence_analyze -p /path/to/pose_dir  # 2Dキーポイント信頼度分析（カメラ別×キーポイント別）
pose_confidence_analyze -p dir -t 0.5 --no-plot  # 閾値変更・プロット省略
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

## 開発方針

- **シンプルな機能を一つずつ作り、積み重ねて目的を達成する**
- 大きな機能を一度に作らない。小さく作って動作確認し、次の機能へ進む

### 機能ごとの開発フロー

各案件（改善ステップ・新機能・バグ修正）について、以下のフローを**厳守**する。**planモードは使わない**（通常モードで調査・計画を行う）。

1. **案件作成** → `docs/{NNN}_{名称}/` フォルダを作成し、`docs/accuracy_improvement_plan.md` に追加する
2. **調査・計画** → 通常モードで既存コードを調査し、要求仕様書（`docs/REQUIREMENTS_STANDARD.md` 準拠）と機能設計書（`docs/DESIGN_STANDARD.md` 準拠）を作成する
3. **ドキュメント保存** → 要求仕様書を `docs/{NNN}_{名称}/requirements.md`、機能設計書を `docs/{NNN}_{名称}/design.md` にファイル保存する。**保存が完了するまで実装に進んではならない**
4. **レビュー（Subagent + 人）** → 保存されたドキュメントをSubagent（Agentツール）でレビューする。ユーザーも同時にレビューする。レビュー実行時は `docs/REVIEW_CRITERIA.md` の基準に従うこと
5. **修正（必要な場合）** → レビューで問題があれば、再調査してドキュメントを更新する。**ステップ2〜4を問題がなくなるまで繰り返す**
6. **引き継ぎ・/clear** → CLAUDE.mdの「現在進行中の案件」セクションを更新し、実装セッションに必要な情報を整える。その後ユーザーが `/clear` を実行
7. **実装** → ドキュメント（要求仕様書・機能設計書・CLAUDE.md）を読んで実装

### ドキュメント作成ルール

- **実装前に必ず「要求仕様書」と「機能設計書」を作成し、案件フォルダにファイル保存すること**
- ドキュメントが保存されていない場合は、**実装を中止**する
- 要求仕様書：何を達成すべきか（入出力、制約、品質基準）。作成時は `docs/REQUIREMENTS_STANDARD.md` の基準に従うこと
- 機能設計書：どう実現するか（モジュール構成、アルゴリズム、データ構造）。作成時は `docs/DESIGN_STANDARD.md` の基準に従うこと
- ドキュメントは `docs/{NNN}_{名称}/` に置く（`requirements.md`, `design.md`）
- **/clear 後でも実装がスムーズにできるよう、必要な情報を全て記述する**
- 暗黙知に頼らず、**自己完結したドキュメント**にする（前の会話コンテキストがなくても実装できること）
- レビュー実行時は `docs/REVIEW_CRITERIA.md` の基準に従うこと
- ライブラリの追加・変更・削除を行った場合は `docs/TECH_STACK.md` も更新すること
- 新規ライブラリ導入時は用途・選定理由・バージョンを `docs/TECH_STACK.md` に追記すること

### テスト

- **テスト実行はSubagent（Agentツール）を使う。** メインの会話コンテキストを消費せず、並列実行も可能にするため
- テスト実行コマンド（Pose2Simパイプライン・精度評価・パラメータ比較など）:
  ```bash
  export MAMBA_EXE='/home/sakagawa/.micromamba/bin/micromamba' && export MAMBA_ROOT_PREFIX='/home/sakagawa/micromamba' && eval "$("$MAMBA_EXE" shell hook --shell bash --root-prefix "$MAMBA_ROOT_PREFIX" 2>/dev/null)" && micromamba activate Pose2Sim && <テストコマンド>
  ```
- **テスト結果は案件フォルダ内にファイル保存する**
  - 保存先: `docs/{NNN}_{名称}/test_results/`
  - 内容: 実行コマンド・出力・trc_evaluate結果などをそのまま保存する

### 管理ドキュメント

- 案件一覧・進捗管理: `docs/accuracy_improvement_plan.md`
- 各案件の詳細: `docs/{NNN}_{名称}/`（`requirements.md`, `design.md`, `README.md`）
- 技術スタック: `docs/TECH_STACK.md`

### セッション開始時

`/clear`や新規セッション開始時は、まず `docs/accuracy_improvement_plan.md` を読んで現在の進捗を把握すること。

## Pose2Simの既知の注意点

調査結果の詳細は各案件ドキュメントを参照: `docs/accuracy_improvement_plan.md`

### ログファイル

- Pose2Simのログは**セッションの親ディレクトリ**に書き込まれる。最新ログは `/home/sakagawa/git/pose2sim/Pose2Sim/logs.txt` を確認すること
- Config.tomlの `save_logs` / `level` は**未実装**（無視される）。認識されるのは `use_custom_logging` のみ

### ローカル修正済みのPose2Simバグ

| ファイル | 内容 | 状態 |
|---------|------|------|
| `triangulation.py` 行929 | C3D変換のジェネレータ式バグ修正 | コミット済み |
| `calibration.py` 行789 | CALIB_FIX_K3除去（k3解放） | 未コミット |
| `calibration.py` 行1499 | distortions 5パラメータ書き出し | 未コミット |
| `calibration.py` 行791-816 | 画像品質フィルタリング追加（案C） | 未コミット |
