# 008: フィルタリングパラメータの調整 [完了]

## 目的

Pose2Simが提供する8種類のフィルタとパラメータを体系的に比較し、最適なフィルタリング設定を特定する。

## 前提

- 三角測量結果（生TRC）は固定（007でnan設定適用済み）
- データ: 30fps, 1770フレーム, 26マーカー (Nyquist=15Hz)
- 5/26マーカーにNaN大ギャップ（0.55%）

## ベースライン

**旧設定**: butterworth, cutoff=6Hz, order=4, reject_outliers=true

| 指標 | 生TRC | フィルタ後(BW) |
|------|-------|---------------|
| Bone CV | 16.7% | 15.4% |
| Smoothness 95%ile | 0.0721 | 0.0139 |
| NaN率 | 0.5% | 0.5% |
| L-R Diff | 3.8% | 4.1% |

## フィルタのNaN対応分類（filtering.py調査結果）

| フィルタ | NaN分割 | ゼロ欠損扱い | テスト対象 |
|---------|---------|------------|----------|
| butterworth | あり | あり | ベースライン |
| kalman | あり | あり | Phase 1-2 |
| gcv_spline | あり | あり | Phase 1 |
| one_euro | あり | なし | Phase 1-2 |
| butterworth_on_speed | あり | あり | Phase 1 |
| loess | あり | なし | Phase 1 |
| gaussian | **なし** | **なし** | 除外 |
| median | **なし** | **なし** | 除外 |

gaussian/medianはNaN非対応のため除外。

## Phase 1: フィルタ種別比較（デフォルトパラメータ）

| ID | type | パラメータ | Bone CV | Smooth | NaN% | L-R Diff |
|----|------|-----------|---------|--------|------|----------|
| P1-01 | butterworth | cutoff=6, order=4 | 15.4% | 0.0139 | 0.5% | 4.1% |
| P1-02 | **kalman** | trust=500, smooth=true | **15.2%** | **0.0082** | 0.5% | 4.2% |
| P1-03 | gcv_spline | auto, sf=1.0 | 15.4% | 0.0147 | 0.5% | 4.1% |
| P1-04 | **one_euro** | cutoff=0.04, beta=5 | **14.7%** | **0.0084** | 0.5% | 4.4% |
| P1-05 | butterworth_on_speed | cutoff=10, order=4 | 20.9% | 0.0306 | 0.0% | 32.1% |
| P1-06 | loess | nb_values=5 | 15.3% | 0.0166 | 0.5% | 4.1% |

**結果**: kalmanとone_euroが明確にベースラインを上回る。butterworth_on_speedはNaN区間で破綻。gcv_spline/loessはベースラインと同等。

## Phase 2: パラメータスイープ

### Kalman trust_ratio

| trust_ratio | Bone CV | Smooth | NaN% | L-R Diff |
|------------|---------|--------|------|----------|
| **100** | **14.6%** | **0.0044** | 0.5% | 4.4% |
| 500 (P1) | 15.2% | 0.0082 | 0.5% | 4.2% |
| 1000 | 15.3% | 0.0109 | 0.5% | 4.1% |
| 5000 | 15.7% | 0.0228 | 0.5% | 4.0% |

trust_ratio↓ = 平滑化↑。BoneCV/Smooth改善、L-R微悪化のトレードオフ。

### One Euro beta

| cutoff/beta | Bone CV | Smooth | NaN% | L-R Diff |
|------------|---------|--------|------|----------|
| 0.04/**1** | **13.1%** | **0.0041** | 0.5% | 5.1% |
| 0.04/5 (P1) | 14.7% | 0.0084 | 0.5% | 4.4% |
| 0.04/10 | 15.2% | 0.0117 | 0.5% | 4.2% |

beta↓ = 均一平滑化。min_cutoff変更（0.01/0.1）はほぼ影響なし、betaが支配的パラメータ。

## Phase 3: reject_outliers効果

| 条件 | reject_outliers | Bone CV | Smooth | NaN% | L-R |
|------|----------------|---------|--------|------|-----|
| one_euro beta=1 | true | 13.1% | 0.0041 | 0.5% | 5.1% |
| one_euro beta=1 | false | 13.0% | 0.0042 | 0.5% | 5.0% |
| kalman tr=100 | true | 14.6% | 0.0044 | 0.5% | 4.4% |
| kalman tr=100 | false | 14.4% | 0.0044 | 0.5% | 4.4% |

**結論**: Hampel前処理の影響はほぼなし（全指標で±0.2pt以内）。三角測量段階のreproj_error閾値で外れ値が既に除去されているため。

## 最終比較

| 設定 | Bone CV | Smooth | NaN% | L-R Diff | 総合 |
|------|---------|--------|------|----------|------|
| butterworth c=6 o=4 (旧BL) | 15.4% | 0.0139 | 0.5% | **4.1%** | - |
| **one_euro beta=1** | **13.1%** | **0.0041** | 0.5% | 5.1% | BoneCV/Smooth最良、L-R悪化 |
| **kalman tr=100** | 14.6% | 0.0044 | 0.5% | 4.4% | バランス型 |

## 結論

### 推奨設定: **kalman, trust_ratio=100, smooth=true**

```toml
[filtering]
type = "kalman"
reject_outliers = true   # 効果小だが害もない

[filtering.kalman]
trust_ratio = 100
smooth = true
```

**選定理由**:
- BoneCV: 15.4% → 14.6% (-0.8pt)
- Smoothness: 0.0139 → 0.0044 (-68%)
- L-R Diff: 4.1% → 4.4% (+0.3pt、許容範囲)
- one_euro beta=1の方がBoneCV/Smoothは良好だが、L-R Diff +1.0pt悪化（4.1→5.1%）が大きく、生体力学的妥当性の観点で不利

### 代替: one_euro beta=1

L-R対称性を重視しない解析（例: 片側のみの関節可動域分析）では、one_euro beta=1がBoneCV/Smoothnessで最良。

## テスト結果ファイル

`pose-3d/008_results/` に全条件のTRCと評価CSVを保存。
