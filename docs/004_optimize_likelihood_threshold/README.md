# 004: likelihood_threshold の最適化 [未着手]

## 1. 目的

`likelihood_threshold_triangulation`（現在値: **0.4**）を最適化し、2Dポーズ検出の信頼度フィルタリングを改善する。

## 2. パラメータの動作

### コード上の動作（triangulation.py）

**Phase 1（三角測量ループ前、L816-L821）**:
```python
x_files[n][likelihood_files[n] < likelihood_threshold] = np.nan
y_files[n][likelihood_files[n] < likelihood_threshold] = np.nan
```
- likelihood値が閾値未満のカメラの2D座標を`NaN`に変換
- **三角測量関数呼び出し前**に実行される → 最も上流のフィルタ
- NaN化されたカメラは以降の処理で完全に無視される

**weighted_triangulation（common.py L327-L354）**:
- likelihood値は三角測量の**重み**としても使用
- likelihood=0.9のカメラはlikelihood=0.4のカメラより2.25倍の重みを持つ

### 他パラメータとの相互作用

- likelihood閾値を上げる → 有効カメラ数が減る → `min_cameras_for_triangulation`の制約に引っかかりやすくなる
- 有効カメラが減ると再投影誤差の計算対象も変わる → `reproj_error_threshold`の判定にも影響

## 3. 現在のベースライン（undistort=true, k3解放後）

| 指標 | 値 |
|------|-----|
| 全体平均再投影誤差 | 11.3 px (~22.8 mm) |
| 平均除外カメラ数 | 0.98台/フレーム |
| Bone CV | 16.4% |
| Smoothness 95%ile | 0.0139 m/frame² |
| NaN率 | 0.0% |
| L-R Diff | 4.9% |

### カメラ別除外率

| カメラ | 除外率 | 特徴 |
|--------|--------|------|
| cam01 | 39% | 望遠/高歪み |
| cam02 | 6% | 広角/低歪み |
| cam03 | 36% | 望遠/高歪み |
| cam04 | 16% | 広角/低歪み |

### カメラ除外が多いキーポイント（現在値0.4で）

| キーポイント | 除外cam数 | 実効カメラ数 |
|------------|----------|------------|
| LWrist | 1.49 | 2.51 |
| LElbow | 1.41 | 2.59 |
| Neck | 1.25 | 2.75 |
| Head | 1.21 | 2.79 |
| Nose | 1.18 | 2.82 |

## 4. テスト条件

| 条件 | likelihood閾値 | 予想効果 |
|------|---------------|---------|
| A | **0.3**（緩和） | カメラ除外↓、ノイズ混入↑ |
| B | **0.4**（現状） | ベースライン |
| C | **0.5**（厳格化） | カメラ除外↑、精度↑（ただしNaN↑の可能性） |
| D | **0.6**（さらに厳格） | カメラ除外↑↑、NaN率が大幅上昇する恐れ |

## 5. 予想される結果

### 0.3に下げた場合
- **カメラ除外が減少** → 実効カメラ数が増加
- **低信頼度の検出が三角測量に参加** → Smoothness悪化の可能性
- NaN率は変化なし（現在0%、fill_large_gaps_with=last_valueのため）
- LElbow/LWristの品質が改善する可能性（より多くのカメラが参加）

### 0.5に上げた場合
- **カメラ除外が増加** → 実効カメラ数が減少
- 特にLWrist/LElbow（現在2.5-2.6台）が2台を切る可能性
- 2台を切るとmin_cameras=2の制約でNaN化 → fill_large_gaps_with=last_valueで補間される
- Bone CV/Smoothnessは改善する可能性があるが、NaN率上昇と補間品質の悪化のリスク

### 0.6に上げた場合
- 現在1.18-1.49台除外されているキーポイントが、2台以上除外に達する可能性大
- 大量のフレームがNaN化 → 実用性の問題
- テストはするが採用の可能性は低い

## 6. テスト手順

各条件について:
1. `Config.toml`の`likelihood_threshold_triangulation`を変更
2. 三角測量 + フィルタリング実行
3. `trc_evaluate`で評価
4. 結果を`pose-3d/likelihood_{値}/`に保存

## 7. 成功基準

| 指標 | 目標 | 比較対象（ベースライン） |
|------|------|----------------------|
| Bone CV | ≤ 16.4% | 16.4% |
| Smoothness | ≤ 0.0139 | 0.0139 |
| L-R Diff | ≤ 4.9% | 4.9% |
| NaN率（フィルタ前TRC） | ≤ 5% | 0% |

Bone CV/Smoothnessが改善し、NaN率が5%以下であれば採用。
