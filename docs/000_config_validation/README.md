# 000: Config.toml の正当性レビュー [完了]

対象: `/home/sakagawa/git/pose2sim/Pose2Sim/20260227-dgtw2-lab2/Config.toml`

## 調査結果サマリ（2026-02-28 再調査）

| 報告された問題 | 原因 | 分類 | 対策 |
|---------------|------|------|------|
| ログが更新されない | `save_logs`/`level`はPose2Simで未実装。ログは別の場所に出力されている | 設定の誤解 | `[logging]`を`use_custom_logging = false`に置換 |
| triangulation()でC3D未生成 | `triangulation.py`行929にPose2Sim本体のバグ（ジェネレータ式の誤用） | ライブラリバグ | 行929を修正 |
| filtering()後のC3D | コードは正しいが、`[filtering]`に`make_c3d`が未設定 | 設定不足 | `make_c3d = true`を追加 |

---

## 問題1: ログが更新されない

### 調査結果

- Config.tomlの`[logging]`セクションにある`save_logs`と`level`はPose2Simコードで**未実装**（完全に無視される）
- 唯一認識されるパラメータは`use_custom_logging`（デフォルト: false）
- ログは常に`{session_dir}/logs.txt`に自動出力される
- `session_dir`の決定ロジック（`Pose2Sim.py`:165-168）:
  - level=1（trial）: cwdの親ディレクトリ。calibrationフォルダが見つからなければcwdにフォールバック
  - level=2（root）: cwd

### 実際のログ状態

- `20260227-dgtw2-lab2/logs.txt`: 2026-02-27 23:35更新（triangulationまで記録）
- `Pose2Sim/logs.txt`: 2026-02-28 00:47更新（全セッションの統合ログ）

### 対策

`[logging]`セクションを以下に置換:
```toml
[logging]
use_custom_logging = false
```

---

## 問題2: triangulation()でC3Dファイルが生成されない

### 調査結果

`triangulation.py` 行929に**Pose2Sim本体のバグ**:

```python
# バグ（修正前）:
c3d_paths.append(convert_to_c3d(t) for t in trc_paths)

# 修正後:
c3d_paths.append(convert_to_c3d(trc_paths[-1]))
```

`append`にジェネレータ式を渡しており、`convert_to_c3d()`が実際に実行されない。ログ行355-356で「All trc files have been converted to c3d.」と出力されるが、実際にはC3Dファイルは未生成。

### 対策

行929を修正済み（ローカルdev install）。

---

## 問題3: filtering()後にC3Dファイルを作れるか

### 調査結果

- `filtering.py` 行748-749のC3D生成コードは**正しい**
- ただしConfig.tomlの`[filtering]`セクションに`make_c3d`が**未設定**だった
- `config_dict.get('filtering').get('make_c3d')` → `None`（False扱い）

### 対策

`[filtering]`セクションに`make_c3d = true`を追加。

---

## 実施した修正一覧

### Config.toml 修正（5箇所）

| # | 変更内容 | 理由 |
|---|---------|------|
| 1a | `path = "..."` 行削除 | コードで完全に未使用のレガシーパラメータ |
| 1b | `project_dir = "..."` 行削除 | 実行時に自動設定される。パスも存在しない |
| 1c | `undistort_points = true` → `false` | 既知問題：再投影誤差悪化（9.9→11.4px） |
| 1d | `[filtering]`に3項目追加 | `make_c3d = true`, `display_figures = false`, `save_filt_plots = true` |
| 1e | `[logging]`セクション置換 | `save_logs`/`level`は未実装。`use_custom_logging = false`のみ有効 |

### triangulation.py バグ修正

- 行929: `c3d_paths.append(convert_to_c3d(t) for t in trc_paths)` → `c3d_paths.append(convert_to_c3d(trc_paths[-1]))`

---

## 前回レビュー（2026-02-27）で正しく設定されていた項目

| 項目 | 値 | 評価 |
|------|-----|------|
| `handle_LR_swap` | `false` | OK（001の対策済み） |
| `pose_model` | `"Body_with_feet"` | OK（HALPE_26相当） |
| `method` | `"DLT"` | OK |
| `min_cameras_for_triangulation` | `2` | OK（4台構成では妥当） |
| `likelihood_threshold_triangulation` | `0.4` | OK（将来0.5も検討可） |
| `reproj_error_threshold_triangulation` | `15.0` | OK |
| butterworth | `6 Hz, order 4` | OK（歩行解析の標準値） |
| mode (YOLOX/RTMPose) | カスタムモデルパス | OK（ファイル存在確認済み） |
| `do_sync` | `false` | OK（事前同期済み） |
| `feet_on_floor` | `false` | OK |
| `use_augmentation` | `true` | OK |

## 検証（2026-02-28 完了）

- [x] `triangulation()` 再実行 → C3Dファイル生成を確認（2026-02-28）
- [x] `filtering()` 再実行 → C3Dファイル生成を確認（2026-02-28）
- [x] ログ出力先の確認（2026-02-28）
