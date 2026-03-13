# 014: 主要人物抽出CLIツール — 機能設計書

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001 | 2.1 JSON読み込み |
| FR-002 | 2.2 人物選択ロジック |
| FR-003 | 2.3 JSON書き出し |
| FR-004 | 2.4 CLIインターフェース |
| FR-005 | 2.5 進捗表示・サマリ |

## 1.2 システム構成

### モジュール構成

```
Pose2Sim/Utilities/pose_extract_person.py  （新規作成、単一ファイル）
```

依存関係: Python標準ライブラリ + numpy + tqdm のみ。他のPose2Simモジュールへの依存なし。

### エントリーポイント登録

`pyproject.toml` の `[project.scripts]` に追加:
```toml
pose_extract_person = "Pose2Sim.Utilities.pose_extract_person:main"
```

## 1.3 技術スタック

| 項目 | 内容 | 理由 |
|------|------|------|
| Python 3.9+ | 既存環境と同一 | |
| numpy | キーポイント配列操作 | 既存依存 |
| tqdm | プログレスバー表示 | 既存依存 |
| json (stdlib) | JSONファイル読み書き | |
| os (stdlib) | パス操作 | |
| sys (stdlib) | エラー出力・終了コード | |
| glob (stdlib) | ファイルパターンマッチ | |
| time (stdlib) | 処理時間計測 | |
| argparse (stdlib) | CLI引数パース | |

新規ライブラリの追加なし。

## 2. 各機能の詳細設計

### 2.1 JSON読み込み（FR-001）

#### データフロー

- **入力**: ディレクトリパス（str）
- **中間**: `sorted(glob(os.path.join(input_dir, '*.json')))` でファイルリスト取得
- **出力**: ファイルパスのソート済みリスト（list[str]）

#### 処理ロジック

```
1. glob でディレクトリ内の *.json を取得
2. ファイル名でソート（sorted）
3. ファイルが0件なら FileNotFoundError を送出
```

#### エラーハンドリング

| エラー | 検出方法 | 処理 |
|--------|---------|------|
| ディレクトリが存在しない | argparseのtype=str + os.path.isdir | エラーメッセージを表示して終了 |
| JSONファイルが0件 | len(files) == 0 | FileNotFoundError送出 |
| JSONパースエラー | json.JSONDecodeError | そのフレームをスキップ（peopleなしとして扱う）、警告を標準エラー出力 |
| `people`キーが存在しない | `data.get('people', [])` で空リスト扱い | peopleなしとして処理を継続 |

### 2.2 人物選択ロジック（FR-002）

#### データフロー

- **入力**: `people` リスト（JSONの `data["people"]`）、前フレームのキーポイント `prev_kp`（`np.ndarray` shape (26, 3) or None）
- **中間**: 有効人物リスト `valid_people`（list[np.ndarray]）
- **出力**: 選択された人物のキーポイント `np.ndarray` shape (26, 3) or None

#### 処理ロジック

`keypoint_jitter_analyze.py` の `_select_person()` 関数をそのまま流用する。ロジックは以下の通り:

```
def _select_person(people, prev_kp):
    # 1. 有効人物のフィルタリング
    valid_people = []
    for person in people:
        kps = person.get('pose_keypoints_2d', [])
        if len(kps) < 26 * 3:
            continue  # キーポイント数不足 → スキップ
        kp = np.array(kps).reshape(26, 3)
        n_valid = np.sum((kp[:, 2] > 0.1) & ~np.isnan(kp[:, 0]))
        if n_valid >= 1:
            valid_people.append(kp)

    # 2. 有効人物が0人 → None
    if not valid_people:
        return None

    # 3. 有効人物が1人 → そのまま返す
    if len(valid_people) == 1:
        return valid_people[0]

    # 4. 前フレームがある場合 → 最も近い人物を選択
    if prev_kp is not None and not np.all(np.isnan(prev_kp)):
        prev_valid = (prev_kp[:, 2] > 0.1) & ~np.isnan(prev_kp[:, 0])
        best_kp, best_dist = None, float('inf')
        for kp in valid_people:
            curr_valid = (kp[:, 2] > 0.1) & ~np.isnan(kp[:, 0])
            shared = prev_valid & curr_valid
            if shared.sum() == 0:
                continue
            dist = np.mean(np.sqrt(np.sum((kp[shared, :2] - prev_kp[shared, :2])**2, axis=1)))
            if dist < best_dist:
                best_dist = dist
                best_kp = kp
        if best_kp is not None:
            return best_kp

    # 5. フォールバック: 有効キーポイント数が最多の人物
    return max(valid_people, key=lambda kp: np.sum(kp[:, 2] > 0.1))
```

#### 境界条件

| 条件 | 振る舞い |
|------|---------|
| `people` が空配列 | `_select_person` 内で `valid_people` が空 → None を返す（呼び出し元の事前チェック不要） |
| 全員の `pose_keypoints_2d` が 78 未満 | `valid_people` が空 → None を返す |
| 前フレームと共有キーポイントが0 | 全候補で共有0なら、フォールバック（有効KP最多）へ |
| 前フレームが None（初回フレーム） | フォールバック（有効KP最多）へ |

### 2.3 JSON書き出し（FR-003）

#### データフロー

- **入力**: 選択結果（np.ndarray or None）、入力JSONファイルパス、出力ディレクトリパス
- **出力**: 出力ディレクトリ内に同名のJSONファイル

#### 処理ロジック

出力JSONはPose2Simの正規フォーマット（`poseEstimation.py:260-273`）に準拠する。

```
1. 出力ファイルパス = os.path.join(output_dir, os.path.basename(input_json_path))
2. 選択結果が None の場合:
     出力JSON = {"version": 1.3, "people": []}
3. 選択結果がある場合:
     kp_list = selected_kp.flatten().tolist()
     出力JSON = {
       "version": 1.3,
       "people": [{
         "person_id": [-1],
         "pose_keypoints_2d": kp_list,
         "face_keypoints_2d": [],
         "hand_left_keypoints_2d": [],
         "hand_right_keypoints_2d": [],
         "pose_keypoints_3d": [],
         "face_keypoints_3d": [],
         "hand_left_keypoints_3d": [],
         "hand_right_keypoints_3d": []
       }]
     }
4. json.dump で書き出し（デフォルトフォーマット、indent なし）
```

#### 設計判断

**JSONフォーマット**:
- 採用: `json.dump(data, fp)` でデフォルトフォーマット（コンパクト）
- 却下: `indent=4` 付き整形出力 → ファイルサイズが大幅増加（97,425ファイル）、Pose2Simは整形不要

### 2.4 CLIインターフェース（FR-004）

#### 処理ロジック

```python
def main():
    parser = argparse.ArgumentParser(
        description='Extract the primary person from multi-person OpenPose JSON files.')
    parser.add_argument('-i', '--input', required=True,
                        help='Input JSON directory')
    parser.add_argument('-o', '--output', default=None,
                        help='Output JSON directory (default: {input}_person)')
    args = parser.parse_args()

    input_dir = args.input
    if not os.path.isdir(input_dir):
        print(f'Error: Input directory not found: {input_dir}', file=sys.stderr)
        sys.exit(1)

    if args.output is None:
        output_dir = input_dir.rstrip('/') + '_person'
    else:
        output_dir = args.output

    os.makedirs(output_dir, exist_ok=True)

    process(input_dir, output_dir)
```

#### 出力ディレクトリ命名

- 入力: `/path/to/cam01_json` → 出力: `/path/to/cam01_json_person`
- 入力: `/path/to/cam01_json/` (末尾スラッシュ) → `rstrip('/')` で除去 → 出力: `/path/to/cam01_json_person`

### 2.5 進捗表示・サマリ（FR-005）

#### 処理ロジック

```
1. tqdm でフレーム処理のプログレスバーを表示（desc='Extracting'）
2. 処理中にカウンタを更新:
   - n_empty: 有効人物0人のフレーム数
   - n_multi: 有効人物2人以上のフレーム数
3. 完了時に以下を print:
   f'Done. {n_frames} frames processed in {elapsed:.1f}s.'
   f'  Empty: {n_empty} ({n_empty/n_frames*100:.1f}%)'
   f'  Multi-person: {n_multi} ({n_multi/n_frames*100:.1f}%)'
```

## 3. ファイル・ディレクトリ設計

### 入出力パス規約

| 項目 | パス |
|------|------|
| 入力 | ユーザー指定のJSONディレクトリ（例: `pose/cam01_json`） |
| 出力 | `-o` 指定 or `{入力}_person`（例: `pose/cam01_json_person`） |

### 出力ファイル命名

入力ファイル名をそのまま使用。例: `frame_000001_00_keypoints.json` → 同名で出力。

## 4. インターフェース定義

### 関数一覧

```python
def _select_person(people: list, prev_kp: np.ndarray | None) -> np.ndarray | None:
    '''Select the best person from detected people.'''

def process(input_dir: str, output_dir: str) -> None:
    '''Process all JSON files: extract primary person and write to output.'''

def main() -> None:
    '''CLI entry point.'''
```

### モジュール内部の処理フロー

```
main()
  ├── argparse で引数解析
  ├── 入力ディレクトリ検証
  ├── 出力ディレクトリ作成
  └── process(input_dir, output_dir)
        ├── glob + sorted でファイルリスト取得
        ├── for each JSON file (with tqdm):
        │     ├── json.load で読み込み
        │     ├── people = data.get('people', [])
        │     ├── _select_person(people, prev_kp) で人物選択
        │     │     （people が空配列でも _select_person 内で valid_people=[] → None 返却で処理される。
        │     │      呼び出し元での事前チェックは不要。防御的に関数内部で完結する設計）
        │     ├── 結果が None → {"version": 1.3, "people": []} を書き出し
        │     ├── 結果が有効 → Pose2Sim正規フォーマット（version, person_id, 全キーポイントフィールド）で書き出し
        │     └── prev_kp を更新（None でない場合のみ）
        └── サマリ出力
```

## 5. ログ・デバッグ設計

本ツールはloggingモジュールを使わず、print/sys.stderrのみで出力する（既存CLIツールと同じ方針）。

| 出力先 | 内容 |
|--------|------|
| stdout | 完了サマリ（フレーム数、空フレーム数、複数人フレーム数、処理時間） |
| stderr | エラーメッセージ（ディレクトリ不在、JSONパースエラー） |
| tqdm | プログレスバー（stderr） |

## 6. 設計判断の記録

### DJ-001: `_select_person` の流用元

- **採用**: `keypoint_jitter_analyze.py` の `_select_person()` をコピーして使用
- **却下**: 共通モジュール化（common.py等に移動） → 現時点で2箇所のみの使用であり、抽象化は時期尚早。将来必要になれば共通化する

### DJ-002: 出力JSONの構造

- **採用**: Pose2Simの正規フォーマット（`poseEstimation.py:260-273`）に準拠。`version`, `person_id`, 全キーポイントフィールドを含む
- **却下（初版の設計、不具合により撤回）**: `{"people": [{"pose_keypoints_2d": [...]}]}` の最小構造 → Pose2Simパイプラインの各ステップ（`personAssociation.py`, `synchronization.py`等）がフィールドの存在を前提としており、欠落するとエラーになる

### DJ-003: CLIオプション名 `-i` / `--input`

- **採用**: `-i` / `--input` を使用
- **却下**: `-p` / `--pose-dir`（既存ツールで使用）
- **理由**: 既存ツール（`keypoint_jitter_analyze.py`, `id_switch_analyze.py`）は複数カメラのposeディレクトリ（`cam*_json` を含む親ディレクトリ）を受け取る。本ツールは単一のJSONディレクトリを受け取るため、汎用的な `-i` / `--input` の方が意味的に正確

### DJ-004: 定数 CONF_THRESHOLD

- **採用**: 0.1 をモジュール内定数として定義（CLIオプションにしない）
- **理由**: `keypoint_jitter_analyze.py` と同じ値。この閾値はNaN埋め空エントリのフィルタリング用であり、ユーザーが変更する必要がない
