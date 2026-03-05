# 011 バウンディングボックスIDスイッチ問題 — 機能設計書（Phase 1）

## 1. 対応要求マッピング

| 要求ID | 設計セクション |
|--------|----------------|
| FR-011-001 | 4. Phase 1 詳細設計 |

**本設計書はPhase 1（FR-011-001）の調査実行方法のみを定義する。Phase 2・3はPhase 1完了後に別途設計する。**

## 2. システム構成

### 分析スクリプト

| ファイル | 役割 |
|---------|------|
| `Pose2Sim/Utilities/id_switch_analyze.py` | IDスイッチ分析CLIツール |

### 依存関係

- 入力: OpenPose形式JSON（既存データ）
- 出力: 分析結果Markdown + CSV
- 外部依存: numpy, pandas, scipy（全て既存環境にインストール済み）

## 3. 技術スタック

- Python 3.11（Pose2Sim環境）
- numpy: 数値計算
- pandas: CSV出力
- scipy: ハンガリアン法（scipy.optimize.linear_sum_assignment）
- json: JSON読み込み（標準ライブラリ）
- tqdm: 進捗表示（既存環境にインストール済み）
- 新規ライブラリの追加なし

## 4. Phase 1 詳細設計: IDスイッチ定量分析

### 4.1 データフロー

```
入力: pose/cam{NN}_json/*.json
  ↓ JSONパース（2フレーム分のみメモリ保持）
  ↓ 各フレームから抽出:
  │   - person_id (list)
  │   - pose_keypoints_2d → reshape(26, 3) → [x, y, conf]
  │   - 検出人数
  ↓ フレーム間比較:
  │   - 検出人数の変動検出
  │   - キーポイント距離行列によるフレーム間人物マッチング（ハンガリアン法）
  ↓ イベントログに記録
  ↓ 統計集計
  ↓
出力: 分析結果ドキュメント + CSV
```

### 4.2 処理ロジック

#### Step 1: JSONパースとデータ抽出

```python
for each camera in [cam01, cam02, cam04]:
    prev_people = None
    events = []  # イベントログ
    match_distances = []  # マッチング距離の全記録

    for each frame_file in sorted(glob(cam_json/*.json)):
        data = json.load(frame_file)
        current_people = []
        for person in data["people"]:
            kp = np.array(person["pose_keypoints_2d"]).reshape(26, 3)  # [x, y, conf]
            # NaN埋め空エントリをフィルタ（有効キーポイントが1つ以上あるpersonのみ）
            if np.all(np.isnan(kp[:, 2])) or not np.any(kp[:, 2] > 0):
                continue  # 空エントリはスキップ
            current_people.append(kp)

        # Step 2, 3 を実行
        # ...

        prev_people = current_people  # 前フレームを更新（2フレーム分のみ保持）
```

**重要: NaN空エントリのフィルタリング**

JSONのpeople配列には全キーポイントがNaNの空エントリが含まれる（例: `len(people)=3`でも有効な人物は1人のみ）。`len(people)`を検出人数としてはならない。有効キーポイント（conf>0かつ非NaN）が1つ以上あるpersonのみ`current_people`に追加する。

#### Step 2: 検出人数変動の検出

```python
# prev_people と current_people の人数を比較
if prev_count != curr_count:
    events.append({
        'frame': frame_idx,
        'event_type': 'count_change',
        'prev_count': prev_count,
        'curr_count': curr_count,
    })
```

#### Step 3: フレーム間人物マッチング（キーポイント距離ベース）

person_idが全て-1のため、キーポイントの空間的近接性で人物を追跡する:

```python
if prev_people is not None and len(current_people) > 0 and len(prev_people) > 0:
    # コスト行列: 各prev-current人物ペアのキーポイント平均距離
    cost_matrix = np.zeros((len(prev_people), len(current_people)))
    for i, prev in enumerate(prev_people):
        for j, curr in enumerate(current_people):
            # conf > 0.1 の共通キーポイントのみ使用
            valid = (prev[:, 2] > 0.1) & (curr[:, 2] > 0.1)
            if valid.sum() >= 3:  # 最低3点は必要
                dist = np.sqrt(((prev[valid, :2] - curr[valid, :2])**2).sum(axis=1)).mean()
                cost_matrix[i, j] = dist
            else:
                cost_matrix[i, j] = float('inf')

    # ハンガリアン法で最小コストマッチング
    from scipy.optimize import linear_sum_assignment
    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    # マッチング距離を全て記録（閾値判定は事後分析で行う）
    for r, c in zip(row_ind, col_ind):
        match_distances.append(cost_matrix[r, c])

    # 未マッチの人物 = 出現/消失
    unmatched_prev = set(range(len(prev_people))) - set(row_ind)
    unmatched_curr = set(range(len(current_people))) - set(col_ind)
    for idx in unmatched_prev:
        events.append({'frame': frame_idx, 'event_type': 'person_lost', ...})
    for idx in unmatched_curr:
        events.append({'frame': frame_idx, 'event_type': 'person_appeared', ...})
```

**設計判断: 固定閾値を使わず、まずマッチング距離の分布を取得する**

Phase 1は調査タスクであるため、IDスイッチ判定の閾値は事前に固定しない。全マッチング距離を記録し、分布の統計量（平均、中央値、95パーセンタイル、99パーセンタイル）を算出する。閾値はPhase 1の結果に基づいて事後的に決定する。

#### Step 4: 検出0フレーム後のマッチング

```python
# 検出0フレームの処理方針:
# - 検出0が発生したフレームはイベントとして記録する
# - 検出0が連続した場合、0になる直前のフレームのデータを保持する
# - 復帰後のフレームで、直前保持データとのマッチングを実施する
# - 消失期間（連続0フレーム数）もイベントに記録する

if len(current_people) == 0:
    # prev_peopleは更新しない（直前の有効データを保持）
    zero_count += 1
    events.append({'frame': frame_idx, 'event_type': 'no_detection', ...})
else:
    if zero_count > 0:
        events.append({'frame': frame_idx, 'event_type': 'detection_resumed',
                       'gap_frames': zero_count, ...})
    zero_count = 0
    # 通常のマッチング処理
```

#### Step 5: パターン分類（事後分析）

全イベントログを集計した後、以下のパターンに分類する:

| パターン | 判定条件 |
|---------|---------|
| A: 一時的消失→再出現 | 検出人数が減少→N_gap フレーム以内に増加（N_gapはfps依存: 30fps×1秒=30フレーム） |
| B: 人数変動なし・マッチング距離異常 | 検出人数変化なし、かつマッチング距離が95パーセンタイルの2倍を超過 |
| C: 段階的な人数変動 | 検出人数が増加後に減少（またはその逆）が10フレーム以内に発生 |
| D: その他 | A-Cのいずれにも該当しない |

**N_gap=30（30fps × 1秒）の根拠**: 対象データセットは30fps。一時的な遮蔽による検出消失は通常1秒以内に復帰する。1秒を超える消失は別の事象として扱う。

### 4.3 CLIインターフェース

```
id_switch_analyze -p <pose_dir> [-o <output_dir>] [--fps <int>]

引数:
  -p, --pose-dir   : poseディレクトリのパス（必須）。cam{NN}_json/ を含む親ディレクトリ
  -o, --output-dir  : 出力先ディレクトリ（デフォルト: docs/011_id_switch_analysis/test_results/）
  --fps             : フレームレート（デフォルト: 30）。パターンAのN_gap計算に使用
```

### 4.4 出力フォーマット

#### CSV（`test_results/id_switch_events.csv`）

```
camera,frame,event_type,prev_person_count,curr_person_count,match_distance,gap_frames,pattern
cam01,523,count_change,3,2,,,
cam01,523,person_lost,3,2,,,A
cam01,528,detection_resumed,2,3,,5,A
```

#### 分析結果ドキュメント（`phase1_results.md`）

以下のセクションを含む:
1. データ概要（フレーム数、カメラ数、fps、検出人数分布）
2. person_idの調査結果（全て-1であることの確認）
3. 検出人数変動の統計（変動回数、変動パターンの分布）
4. フレーム間マッチング距離の分布統計（カメラごとの平均値、中央値、95パーセンタイル、99パーセンタイル）
5. パターン別の集計
6. 手動検証（先頭50フレームの分析結果と目視確認の一致度）
7. 考察（主な問題パターンの特定）

### 4.5 エラーハンドリング

| エラー | 処理 |
|--------|------|
| JSONパースエラー | WARNING出力（`WARNING: {camera} frame {N}: JSON parse error`）してスキップ。エラーフレーム数を最終レポートに記載 |
| 検出人数0のフレーム | イベントとして記録。直前の有効データを保持 |
| キーポイント座標が全て0 | conf=0として扱い、マッチング計算から除外 |
| 全キーポイントがNaN（空エントリ） | 人物として扱わない（検出人数にカウントしない）。JSONのpeople配列にはNaN埋めの空エントリが含まれるため |
| 有効キーポイント3点未満の人物 | マッチング対象から除外、WARNINGとして記録 |

### 4.6 境界条件

- 最初のフレーム: 前フレームなしのためマッチングスキップ
- 単一人物のみのフレーム: マッチングは1対1で実施
- 全キーポイントがconf < 0.1の人物: マッチング対象から除外

### 4.7 ログ・進捗表示

- tqdmでカメラごとのフレーム処理進捗を表示
- WARNING時のフォーマット: `WARNING: {camera} frame {frame_idx}: {message}`
- 処理完了時に各カメラのサマリ統計を標準出力に表示

## 5. 設計判断の記録

### 採用: キーポイント距離ベースのマッチング
- 理由: person_idが全て-1のため、ID変化の検出ではなく空間的追跡が必要
- 却下案: person_idの変化検出 → IDが全て-1なので不可能

### 採用: ハンガリアン法（scipy.optimize.linear_sum_assignment）
- 理由: 最適なマッチングを保証する標準的手法。Pose2Sim環境にscipyが既にインストール済み
- 却下案: 最近傍マッチング → 交差マッチングが発生する可能性

### 採用: 閾値を事後的に決定する設計
- 理由: Phase 1は調査タスクであり、事前に閾値を固定するとデータの特性を見逃す可能性がある
- 却下案: 100pxの固定閾値 → 解像度やカメラ距離に依存し、根拠が不十分

### 採用: 2フレーム分のみメモリ保持
- 理由: 10.8万フレーム×3カメラのデータを全てメモリに載せる必要がない。マッチングは前フレームとの比較のみ
- イベントログは軽量なdictリストとして蓄積（最大でも数千件程度）
