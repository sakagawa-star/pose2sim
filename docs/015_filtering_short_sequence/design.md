# 015: Kalmanフィルタの短シーケンスクラッシュ修正 — 機能設計書

## 1.1 対応要求マッピング

| 要求ID | 設計セクション |
|--------|---------------|
| FR-001 | 1.4 修正内容 |

## 1.2 システム構成

変更対象ファイル: `Pose2Sim/filtering.py`
変更対象関数: `kalman_filter_1d`（428行目）

他のファイル・関数への変更なし。

## 1.3 技術スタック

変更なし。既存のPose2Simの依存関係のみ使用。

## 1.4 修正内容（FR-001）

### 原因

`kalman_filter_1d`（428行目）のシーケンス長チェック:
```python
idx_sequences_to_filter = [seq for seq in idx_sequences if len(seq) >= 2]
```

これにより長さ2〜3のシーケンスが `kalman_filter` に渡される。`kalman_filter` は `nb_derivatives=3` で呼ばれ、初期状態計算（350行目）で `np.diff` を最大2回適用する:

- `n_der=0`: diffなし → 元の配列（長さN）
- `n_der=1`: diff 1回 → 長さ N-1
- `n_der=2`: diff 2回 → 長さ N-2

N=2の場合、N-2=0となり空配列に `[0]` でアクセスして `IndexError`。
N=3の場合、N-2=1で `[0]` アクセスは成功するが、`batch_filter` に渡すデータが極端に短く、フィルタとしての意味がない。

### 修正方法

428行目の条件を `nb_derivatives + 1` 以上に変更する。`nb_derivatives=3` のため、最低4フレーム必要:

**変更前（428行目）:**
```python
idx_sequences_to_filter = [seq for seq in idx_sequences if len(seq) >= 2]
```

**変更後:**
```python
idx_sequences_to_filter = [seq for seq in idx_sequences if len(seq) >= 4]
```

### 設計判断

| 判断 | 採用案 | 却下案 | 理由 |
|------|--------|--------|------|
| 最低長の値 | 固定値 `4` | `nb_derivatives + 1` を動的計算 | `kalman_filter_1d` 内で `nb_derivatives` は直接参照できない（`kalman_filter` に `nb_derivatives=3` でハードコード渡し）。動的にするには関数シグネチャ変更が必要で、不具合修正の範囲を超える |
| 短シーケンスの扱い | フィルタリングせず元の値を保持 | NaNで埋める | 2〜3フレームでも有効な座標データであり、消す理由がない |

### 他のフィルタへの影響

同じ `len(seq) >= 2` パターンが存在する他の関数は問題なし:

| 行 | 関数 | 理由 |
|----|------|------|
| 148 | `one_euro_filter_1d` | `np.diff` は1回のみ（速度計算）。長さ2で動作可能 |
| 274 | `gcv_spline_filter_1d` | スプラインフィッティング。長さ2で動作可能 |
| 465 | `butterworth_filter_1d` | 別条件 `len(seq) > padlen` を使用。問題なし |
| 503 | `butterworth_on_speed_filter_1d` | 同上 |

## 1.5 テスト方法

1. **クラッシュ修正の確認**: `20260319-dgtw-lab2` のConfig.tomlでkalmanフィルタを指定した状態で `Pose2Sim.filtering()` を実行し、エラーなく完了すること、出力TRCファイルが生成されることを確認する
2. **回帰テスト**: 修正前に正常完了していたデータセット（`20260227-dgtw2-lab2`）に対してkalmanフィルタを実行し、出力TRCが修正前と同一であることを `trc_evaluate` で確認する（BoneCV・Smoothness・NaN率・L-R対称性が修正前の値と一致）
