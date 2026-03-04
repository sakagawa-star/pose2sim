# docs/TECH_STACK.md

技術スタック一覧（2026-03-04 作成）

---

## プロジェクト基盤

| 項目 | 値 | 根拠 |
|------|-----|------|
| 言語 | Python | `pyproject.toml` |
| Pythonバージョン | >=3.9 | `pyproject.toml` `requires-python = ">=3.9"` |
| パッケージ管理 | pip + setuptools（setuptools-scm でバージョン自動生成） | `pyproject.toml` `[build-system]` |
| 対象OS | OS Independent | `pyproject.toml` classifiers `Operating System :: OS Independent` |
| ビルドバックエンド | setuptools.build_meta | `pyproject.toml` `[build-system]` |
| バージョン管理 | gitタグから動的生成（`setuptools-scm`） | `pyproject.toml` `dynamic = ["version"]` |

---

## ライブラリ一覧

### コアデータ処理・科学計算

| ライブラリ名 | バージョン指定 | 用途（1行） | 使用箇所（モジュール名） | 選定理由（1行） |
|-------------|--------------|------------|------------------------|----------------|
| numpy | `<2.0` (Python<3.12), `>=2.0,<2.3` (Python>=3.12) | 数値計算・配列操作全般 | Pose2Sim.py, calibration.py, triangulation.py, filtering.py, common.py, poseEstimation.py, kinematics.py, personAssociation.py, markerAugmentation.py, 各Utilities (計33ファイル以上) | 科学計算の標準ライブラリ |
| pandas | `>=1.5` | TRCファイル読み書き・表形式データ操作 | calibration.py, common.py, filtering.py, synchronization.py, 各Utilities (計17ファイル) | 表形式データ処理の標準ライブラリ |
| scipy | 未固定（バージョン指定なし） | 信号処理・補間・最適化 | filtering.py, triangulation.py, trc_filter.py, trc_plot.py, trc_gaitevents.py, bodykin_from_mot_osim.py | Butterworth/Kalmanフィルタ、スプライン補間等に使用 |
| statsmodels | 未固定（バージョン指定なし） | LOESS平滑化・統計モデリング | filtering.py, trc_filter.py, trc_plot.py | LOESS/LOWESSフィルタの実装に使用 |
| filterpy | 未固定（バージョン指定なし） | カルマンフィルタ実装 | filtering.py | カルマンフィルタの参照実装 |

### コンピュータビジョン・画像処理

| ライブラリ名 | バージョン指定 | 用途（1行） | 使用箇所（モジュール名） | 選定理由（1行） |
|-------------|--------------|------------|------------------------|----------------|
| opencv-python (cv2) | `!= 4.11.*`（4.11系を除外） | カメラキャリブレーション・画像処理・歪み補正 | calibration.py, poseEstimation.py, triangulation.py, filtering.py, common.py, synchronization.py, markerAugmentation.py, 各Utilities (計16ファイル) | OpenCVはコンピュータビジョンの標準ライブラリ |
| PIL (Pillow) | 未固定（`pyproject.toml`に記載なし） | 画像メタデータ読み取り | calibration.py | **不整合**: コードでimportされるが`pyproject.toml`のdependenciesに未記載 |

### 姿勢推定・推論

| ライブラリ名 | バージョン指定 | 用途（1行） | 使用箇所（モジュール名） | 選定理由（1行） |
|-------------|--------------|------------|------------------------|----------------|
| rtmlib | 未固定（バージョン指定なし） | RTMPose/RTMO姿勢推定モデルの実行 | poseEstimation.py, face_blurring.py | リアルタイム姿勢推定のための軽量ライブラリ |
| openvino | 未固定（バージョン指定なし） | 推論バックエンド（CPU環境でのポーズ推定） | poseEstimation.py（rtmlib経由で間接使用） | CPU環境での高速推論バックエンド |
| onnxruntime | 未固定（バージョン指定なし） | ONNXモデル推論（MarkerAugmenter LSTM等） | markerAugmentation.py | LSTMマーカー拡張モデルの実行に使用 |
| mediapipe | 未固定（`pyproject.toml`に記載なし） | BlazePose姿勢推定 | Blazepose_runsave.py | **不整合**: コードでimportされるが`pyproject.toml`のdependenciesに未記載 |

### 骨格・ツリー構造

| ライブラリ名 | バージョン指定 | 用途（1行） | 使用箇所（モジュール名） | 選定理由（1行） |
|-------------|--------------|------------|------------------------|----------------|
| anytree | 未固定（バージョン指定なし） | 骨格階層（キーポイント接続）のツリー表現 | skeletons.py, poseEstimation.py, calibration.py, kinematics.py, personAssociation.py, common.py, synchronization.py, triangulation.py | ツリー構造を直感的に定義・操作できるライブラリ |

### バイオメカニクス

| ライブラリ名 | バージョン指定 | 用途（1行） | 使用箇所（モジュール名） | 選定理由（1行） |
|-------------|--------------|------------|------------------------|----------------|
| opensim | 未固定（`pyproject.toml`に記載なし） | OpenSimによる逆運動学・運動解析 | kinematics.py, bodykin_from_mot_osim.py, trc_from_mot_osim.py | **不整合**: コードでimportされるが`pyproject.toml`のdependenciesに未記載（外部インストール前提） |
| lxml | 未固定（バージョン指定なし） | XML（OpenSim設定ファイル）の読み書き | calibration.py, kinematics.py, calib_qca_to_toml.py, calib_toml_to_qca.py | OpenSim XMLファイルのパース用 |

### ファイル形式・設定

| ライブラリ名 | バージョン指定 | 用途（1行） | 使用箇所（モジュール名） | 選定理由（1行） |
|-------------|--------------|------------|------------------------|----------------|
| toml | 未固定（バージョン指定なし） | Config.toml設定ファイルの読み書き | Pose2Sim.py, calibration.py, personAssociation.py, common.py, triangulation.py, 各Utilities (計11ファイル) | TOML形式の設定ファイルパーサー |
| c3d | 未固定（バージョン指定なし） | C3Dモーションキャプチャ形式の読み書き | trc_to_c3d.py, c3d_to_trc.py, common.py | C3D形式はバイオメカニクスの標準形式 |

### 可視化・GUI

| ライブラリ名 | バージョン指定 | 用途（1行） | 使用箇所（モジュール名） | 選定理由（1行） |
|-------------|--------------|------------|------------------------|----------------|
| matplotlib | 未固定（バージョン指定なし） | グラフ描画・ヒートマップ生成 | calibration.py, filtering.py, synchronization.py, common.py, trc_filter.py, trc_plot.py, trc_gaitevents.py, json_display_without_img.py | Python標準のグラフ描画ライブラリ |
| mpl_interactions | 未固定（バージョン指定なし） | matplotlibのインタラクティブ機能拡張 | calibration.py | キャリブレーション可視化でのインタラクティブ操作 |
| PyQt5 | 未固定（バージョン指定なし） | matplotlibのGUIバックエンド | calibration.py, trc_filter.py, trc_plot.py, common.py | matplotlib GUIバックエンドとして使用 |
| cmapy | 未固定（`pyproject.toml`に記載なし） | OpenCV用カラーマップ変換 | json_display_with_img.py | **不整合**: コードでimportされるが`pyproject.toml`のdependenciesに未記載 |
| customtkinter | 未固定（バージョン指定なし） | GUI（Pose2Simメインアプリケーション） | GUIモジュール（`GUI/main.py`、現時点でファイル未存在） | tkinterのモダンUI拡張 |

### ユーティリティ

| ライブラリ名 | バージョン指定 | 用途（1行） | 使用箇所（モジュール名） | 選定理由（1行） |
|-------------|--------------|------------|------------------------|----------------|
| tqdm | 未固定（バージョン指定なし） | プログレスバー表示 | poseEstimation.py, personAssociation.py, face_blurring.py, triangulation.py | 長時間処理の進捗表示用 |
| ipython | 未固定（バージョン指定なし） | インタラクティブPythonシェル | 未定義（実コードでのimport未確認） | 開発・デバッグ用途と推定 |
| requests | 未固定（バージョン指定なし） | HTTP通信 | 未定義（実コードでのimport未確認） | 用途未定義 |

### pyproject.toml記載だが実コードでimport未確認

| ライブラリ名 | バージョン指定 | 備考 |
|-------------|--------------|------|
| customtkinter | 未固定 | `GUI/main.py`用と推定されるがGUIモジュール自体が未存在 |
| ipython | 未固定 | 開発用依存と推定、実コードでのimport未確認 |
| requests | 未固定 | 用途不明、実コードでのimport未確認 |

### 実コードでimportされるがpyproject.toml未記載

| ライブラリ名 | importファイル | 備考 |
|-------------|--------------|------|
| PIL (Pillow) | calibration.py | opencv-pythonの依存で間接インストールされる可能性あり |
| mediapipe | Blazepose_runsave.py | Google MediaPipe、オプショナル機能用 |
| opensim | kinematics.py, bodykin_from_mot_osim.py, trc_from_mot_osim.py | conda/pip外のインストール（公式バイナリ）が必要 |
| cmapy | json_display_with_img.py | OpenCV用カラーマップユーティリティ |

---

## バージョン固定ポリシー

### バージョン管理ファイル

- **`pyproject.toml`** の `[project] dependencies` セクションで一元管理
- `requirements.txt`、`environment.yml`、`setup.py` は存在しない
- ビルドシステム依存は `[build-system] requires` で管理: `setuptools>=45`, `wheel`, `setuptools-scm`

### バージョン指定の方針

| 方針 | 対象ライブラリ | 例 |
|------|--------------|-----|
| **条件付きバージョン範囲** | numpy | `<2.0` (Python<3.12), `>=2.0,<2.3` (Python>=3.12) |
| **下限指定 (>=)** | pandas | `>=1.5` |
| **特定バージョン除外 (!=)** | opencv-python | `!= 4.11.*`（回転メタデータのバグ回避） |
| **バージョン未指定** | その他全ライブラリ | `toml`, `scipy`, `matplotlib` 等 |

大多数のライブラリはバージョン未指定（最新版に依存）。`==`による完全固定は使用されていない。

---

## 制約・禁止事項

### 要求仕様書・設計書からの制約

#### 010: pose_confidence_analyze

- **NFR-2**: 依存ライブラリは `numpy`, `matplotlib` のみ。`pandas`は使用しない（JSONから直接numpy配列へ）
- 出典: `docs/010_2d_confidence_analysis/requirements.md`

#### 009: trc_evaluate

- **依存関係**: `numpy`のみ。追加パッケージ不要
- 出典: `docs/009_quantitative_accuracy_evaluation/README.md`

### opencv-pythonバージョン制約

- **4.11系は使用禁止**: 回転メタデータ（displaymatrix）が無視されるバグのため
- 出典: `pyproject.toml` コメント `# avoid 4.11 due to displaymatrix ignored (rotation metadata)`

### deep-sort-realtime

- **コメントアウト済み**: `pyproject.toml`で `# "deep-sort-realtime"` としてコメントアウト。`# likely not required anymore` との注記あり
- 現在は依存に含まれない

### 使用禁止ライブラリ

- 要求仕様書（`docs/REQUIREMENTS_STANDARD.md`）に使用禁止ライブラリの項目テンプレートが存在するが、具体的な禁止ライブラリの記載は**未定義**（010のpandas不使用制約を除く）

### その他の制約

- プロジェクト全体での使用禁止ライブラリ一覧: **未定義**
- ネットワーク制約: **未定義**
- ファイルサイズ・メモリ使用量の制約: **未定義**
