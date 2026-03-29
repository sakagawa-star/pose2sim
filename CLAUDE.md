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
| `20251024_osaka-hosp.PortalCam.01hour/` | 大阪病院、PortalCam、1時間（3cam, 10.8万フレーム, 常時3人検出, 30fps）★011調査対象 |
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
id_switch_analyze -p /path/to/pose_dir        # IDスイッチ分析（検出人数変動・フレーム間マッチング）
id_switch_analyze -p dir -o output/ --fps 30  # 出力先・FPS指定
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

### 不具合修正フロー

既存実装に不具合が見つかった場合、以下のフローを**厳守**する。「問題が明白だからすぐ直せる」場合でも省略不可。

1. **調査** → 原因を特定し、調査結果をユーザーに報告する。**報告で止まる。コード修正に進んではならない**
2. **ユーザー判断** → ユーザーが修正方針を決定する
3. **設計書更新** → 該当案件の機能設計書を修正する
4. **実装** → 設計書に基づいてコードを修正する

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

## 現在進行中の案件（2026-03-29）

| 管理番号 | 状態 | 実装するスクリプト | 次のアクション |
|---------|------|-------------------|--------------|
| 011 | **Phase 1完了** | `id_switch_analyze.py`（実装済み） | — |
| 012 | **Phase 1完了・調査停止中** | `keypoint_jitter_analyze.py`（実装済み） | 動画確認後にPhase 2着手判断 |
| 013 | **Phase 1実装待ち** | `head_keypoint_analyze.py` | `requirements.md`と`design.md`を読んで実装 |
| 014 | **機能設計書作成待ち** | `pose_extract_person.py` | 機能設計書を作成→実装 |
| 016 | **完了** | `pose_overlay_video.py`（実装済み） | — |
| 017 | **完了** | `confidence_timeline.py`（実装済み） | — |
| 018 | **完了** | `pose_overlay_video.py`（confidence閾値フィルタ追加） | — |
| 019 | **要求仕様書・機能設計書作成待ち** | `pose_overlay_video.py`（MP4動画背景対応） | 要求仕様書・機能設計書を作成→実装 |

### 014: 主要人物抽出CLIツール（pose_extract_person）

**目的**: OpenPose形式のJSONディレクトリから、主要人物（患者）のみを抽出して新しいJSONディレクトリに書き出すCLIツール。

**背景**:
- `20150910_osaka_hosp` のデータ（97,425フレーム、単一カメラ）で、168フレームに看護師が映り込んでいる
- `personAssociation()`は複数カメラ間の対応付けであり、単一カメラ内のフレーム間追跡には使えない
- `keypoint_jitter_analyze.py`の`_select_person`関数（前フレーム追跡ロジック）を流用する

**想定CLI**:
```
pose_extract_person -i <入力JSONディレクトリ> -o <出力JSONディレクトリ>
```

**実装の参考**:
- `keypoint_jitter_analyze.py`の`_select_person()`関数: 前フレームとのキーポイント距離で同一人物を追跡
- `pose_confidence_analyze.py`, `id_switch_analyze.py`: CLIパターン・エントリーポイント登録方法
- **pyproject.tomlにエントリーポイント追加が必要**: `pose_extract_person = "Pose2Sim.Utilities.pose_extract_person:main"`

**人物選択ロジック**:
1. people配列から有効人物（conf > 0.1のキーポイントが1つ以上）をフィルタ
2. 1人のみ → そのまま選択
3. 複数人 → 前フレームの人物に最も近い人物を選択（共有キーポイントの平均距離）
4. 前フレームがない場合 → 有効キーポイント数が最多の人物を選択

**既存の実行実績**: `20150910_osaka_hosp`データで実行済み。97,425フレームを約10秒で処理、168フレームの複数人フレームで患者を正しく選択

### 012の現状（調査停止中）

- `keypoint_jitter_analyze.py` 実装済み、`pyproject.toml` エントリーポイント追加済み
- Phase 1分析完了: 6,627件の暴れイベント検出。パターンE(68.7%)が全カメラ共通→RTMpose推定の揺らぎが主因
- 足先の暴れは障害物遮蔽（想定通り）。上半身はLWrist(272件)とHead/Ear(191-228件)がやや多い
- **動画確認が未実施**: フレーム985/935/1000/1020付近のパターンE多発箇所を確認する必要あり
- 詳細は `docs/012_2d_keypoint_jitter/phase1_results.md` を参照

### 012の追加改修（未コミット）

- `keypoint_jitter_analyze.py`に`_select_person()`関数を追加（複数人フレーム対応）
- ディレクトリ検索パターン拡張: `cam*_json` → `*_json` → 直接JSONディレクトリのフォールバック
- `20150910_osaka_hosp`データで暴れ分析を実行済み（結果: `/tmp/jitter_20150910/`）

### 013実装の参考情報

- **011/012の実装パターンを踏襲**: `id_switch_analyze.py`, `keypoint_jitter_analyze.py`, `pose_confidence_analyze.py` が既存の類似CLIツール
- **pyproject.tomlにエントリーポイント追加が必要**: `head_keypoint_analyze = "Pose2Sim.Utilities.head_keypoint_analyze:main"`
- **pip install -e .** でエントリーポイントを反映してからテスト実行

### 重要: HALPE_26キーポイントインデックスの2つの順序体系

JSON配列（2Dデータ）とTRC列（3Dデータ）でキーポイントの順序が異なる。混同しないこと。

| キーポイント | JSON idx (skeletons.py id) | TRC列順 (ツリー走査) |
|---|---|---|
| Nose | **0** | 15 |
| LEye | **1** | 16 |
| REye | **2** | 17 |
| LEar | **3** | 18 |
| REar | **4** | 19 |
| Head | **17** | 14 |
| Neck | **18** | 13 |
| Hip | **19** | 0 |

2D分析スクリプトではJSON idx（skeletons.py id属性）を使用する。3D分析ではTRCのマーカー名でアクセスする。

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
