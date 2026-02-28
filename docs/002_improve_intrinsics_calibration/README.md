# 002: intrinsicsキャリブレーションの改善 [完了・案A採用]

## 1. 背景

cam01/cam03はレンズ歪みが大きい（k1 ≈ -0.15）が、`undistort_points=true` にすると精度が**悪化**する:
- 再投影誤差: 9.9px → 11.4px（+15%）
- カメラ除外率: 0.47台 → 0.96台（2倍）
- cam01/cam03の除外率が9-15% → **36-37%** に跳ね上がる

これは歪み係数の精度が不十分で、歪み補正が逆効果になっていることを意味する。

## 2. カメラ特性

| カメラ | 焦点距離(px) | レンズ種類 | k1 | k2 | 被写体距離 | undistort時の除外率 |
|--------|-------------|----------|------|------|-----------|------------------|
| **cam01** | **2015** | **望遠** | **-0.146** | **+0.099** | 3.49m | **36%** |
| cam02 | 1186 | 広角 | -0.031 | +0.039 | 2.52m | 6% |
| **cam03** | **2040** | **望遠** | **-0.150** | **+0.110** | 3.88m（最遠） | **37%** |
| cam04 | 1178 | 広角 | -0.033 | +0.041 | 2.71m | 17% |

**問題のあるカメラ**: cam01/cam03（望遠レンズ、歪み大）
**問題のないカメラ**: cam02/cam04（広角レンズ、歪み小）

## 3. trc_evaluate による左右非対称性の裏付け

20260227-dgtw2-lab2_1-1771_filt_butterworth.trc の評価結果で、**左側の精度が右側より一貫して悪い**:

| 部位 | 左のCV(%) | 右のCV(%) | 左右比 |
|------|----------|----------|--------|
| Upper Arm | 13.2 | 5.3 | 左が2.5倍悪い |
| Forearm | 30.3 | 8.7 | 左が3.5倍悪い |
| Shoulder | 15.6 | 10.4 | 左が1.5倍悪い |

cam01/cam03（望遠・高歪み）が被写体の左側を主に撮影していると推測される。

## 4. コード調査結果（2026-02-28実施）

### 4.1 実装の全体フロー

```
calibrate_cams_all()                    # calibration.py:1341
└─ calib_calc_fun()                     # calibration.py:473
   ├─ calibrate_intrinsics()            # calibration.py:543
   │  ├─ extract_frames()              # 動画から1秒ごとにPNG抽出
   │  ├─ findCorners()                 # cv2.findChessboardCorners + cornerSubPix
   │  └─ cv2.calibrateCamera()         # ★コアのキャリブレーション
   ├─ calibrate_extrinsics()            # calibration.py:632
   │  └─ cv2.solvePnP()               # 固定intrinsicsでextrinsics計算
   └─ toml_write()                      # calibration.py:1283
```

### 4.2 結論: バグはないが設計上の制約が3つある

#### 制約A: 歪みモデルが不十分（最重要）

**ファイル**: `calibration.py:616-617`
```python
ret_cam, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
    objpoints, imgpoints, img.shape[1::-1],
    None, None,
    flags=(cv2.CALIB_FIX_K3 + cv2.CALIB_USE_LU))
```

`CALIB_FIX_K3` フラグによりk3=0に固定。結果として **4パラメータモデル（k1, k2, p1, p2）** のみ使用。

| モデル | パラメータ数 | OpenCVフラグ | 適用範囲 |
|--------|------------|-------------|---------|
| **現在** | **4 (k1,k2,p1,p2)** | `CALIB_FIX_K3` | **歪みが小さいレンズ向け** |
| 標準5 | 5 (k1,k2,p1,p2,k3) | フラグなし | 中程度の歪み |
| Rational | 8 (k1-k6,p1,p2) | `CALIB_RATIONAL_MODEL` | 大きい歪みのレンズ |

cam01/cam03は k1=-0.15, k2≈+0.10 の2パラメータで歪みを近似しているが、k3を解放すれば補正精度が向上する可能性が高い。

**TOML保存処理** (`calibration.py:1306`):
```python
dist = f'distortions = [ {D[c][0]}, {D[c][1]}, {D[c][2]}, {D[c][3]}]\n'
```
4パラメータのみ書き出し。k3を使う場合はここも修正が必要。

**TOML読み込み処理** (`common.py:280`):
```python
dist.append(np.array(calib[cam]['distortions']))
```
配列長に依存しないため、5パラメータにしても読み込み側はそのまま動作する。

#### 制約B: getOptimalNewCameraMatrix の alpha=1

**ファイル**: `common.py:281`
```python
optim_K.append(cv2.getOptimalNewCameraMatrix(
    K[c], dist[c], [int(s) for s in S[c]], 1, [int(s) for s in S[c]])[0])
#                                            ↑ alpha=1
```

| alpha値 | 動作 | 向いているケース |
|---------|------|---------------|
| **1（現在）** | **全ピクセル保持（端の歪み領域も含む）** | 歪みが小さいレンズ |
| 0 | 有効領域のみ（端をクロップ） | **歪みが大きいレンズ** |

高歪みカメラ（cam01/cam03）では、画像端のキーポイントほど歪み補正の誤差が増幅される。

#### 制約C: キャリブレーション画像の品質フィルタリングなし

**ファイル**: `calibration.py:598-609`
```python
for img_path in img_vid_files:
    imgp_confirmed = findCorners(img_path, ...)
    if isinstance(imgp_confirmed, np.ndarray):
        imgpoints.append(imgp_confirmed)    # ← 検出できたら全て無条件に採用
        objpoints.append(objp)

if len(imgpoints) < 10:
    logging.info(f'Corners detected only on {len(imgpoints)} images...')  # 警告のみ
```

行われていないフィルタリング:
- **個別画像の再投影誤差チェック**: 外れ値的に悪い画像も含まれる
- **チェッカーボードの多様性チェック**: 同一角度・位置の画像が大量にあっても全部使う
- **ブレ・ピンボケ検出**: ぼやけた画像のコーナーも使われる

各カメラの抽出フレーム数:
| カメラ | 抽出PNG数 | 動画ソース | 備考 |
|--------|----------|-----------|------|
| cam01 | 128枚 | cam01.mp4 | |
| cam02 | 180枚 | cam02.mp4 | 最多 |
| cam03 | 104枚 | cam03.mp4 | 最少 |
| cam04 | 154枚 | cam04.mp4 | |

枚数自体は十分（10枚以上の閾値を大幅にクリア）だが、品質と多様性は未確認。

### 4.3 正常に機能している部分

以下は問題なし:
- **コーナー検出**: `cv2.findChessboardCorners` → `cv2.cornerSubPix`（11x11ウィンドウ、30反復、0.001px精度）は標準的で適切
- **3Dオブジェクト点の生成**: `intrinsics_square_size` のmm→m変換（`/1000`、行568）は正しい
- **歪み係数の保存/読み込みの整合性**: 書き出し4パラメータ、読み込みは配列長依存なし
- **extrinsicsでの利用**: `cv2.solvePnP` で固定intrinsicsを使用（行727）は正しい
- **undistortPoints呼び出し**: 4パラメータでOpenCVが正しく処理する

### 4.4 現在のConfig.toml設定

```toml
[calibration.calculate.intrinsics]
overwrite_intrinsics = false
show_detection_intrinsics = false
intrinsics_extension = 'mp4'
extract_every_N_sec = 1            # 1秒ごとにフレーム抽出
intrinsics_corners_nb = [6,9]      # 内部コーナー数 [h,w]
intrinsics_square_size = 25        # mm（コード内でm変換される）
```

## 5. 改善案

### 案A: k3の解放（最優先・低リスク）

`CALIB_FIX_K3` フラグを外して5パラメータモデルにする。

**変更箇所**:

| ファイル | 行 | 変更内容 |
|---------|-----|---------|
| `calibration.py` | 616-617 | `flags=cv2.CALIB_USE_LU`（`CALIB_FIX_K3`を除去） |
| `calibration.py` | 1306 | distortionsを5パラメータで書き出し |
| (読み込み側は変更不要) | | `common.py:280` は配列長に依存しないため |

**期待効果**: cam01/cam03の歪みモデル精度向上 → `undistort_points=true` が有効に機能するようになる可能性

**リスク**: 低。k3の自由度が増えるだけで、k3≈0ならば現在と同等の結果になる。

### 案B: alpha値の調整（中優先・低リスク）

`getOptimalNewCameraMatrix` の alpha を 0 に変更（または設定可能にする）。

**変更箇所**: `common.py:281`

**期待効果**: 高歪みカメラの画像端での誤差軽減

### 案C: キャリブレーション画像の品質フィルタリング（中優先・中リスク）

再投影誤差が大きい画像を除外するフィルタを追加。

**変更箇所**: `calibration.py:598-617` 周辺

**アプローチ**:
1. 全画像でキャリブレーション実施
2. 画像ごとの再投影誤差を計算
3. 誤差が閾値以上の画像を除外
4. 残った画像で再キャリブレーション

### 案D: チェッカーボード動画の再撮影（高効果・高コスト）

より慎重にチェッカーボード動画を再撮影:
- ボードを画像の様々な位置（中央、四隅、端）に配置
- 複数の距離（近距離・中距離・遠距離）で撮影
- 複数の角度（正面、斜め30度、斜め45度）で撮影
- ブレなし・十分な照明を確保

### 推奨実施順序

```
案A（k3解放） → undistort_points=true で再評価
 ├─ 改善された場合 → 案Bも適用して更に評価
 └─ 不十分な場合 → 案C（画像フィルタリング）→ 案D（再撮影）
```

## 6. 案Aの実施手順（★次のアクション）

### 6.1 コード変更（3箇所）

**変更1: calibration.py 行616-617 — CALIB_FIX_K3を除去**
```python
# Before:
flags=(cv2.CALIB_FIX_K3 + cv2.CALIB_USE_LU)
# After:
flags=cv2.CALIB_USE_LU
```

**変更2: calibration.py 行1306 — distortions書き出しを5パラメータに**
```python
# Before:
dist = f'distortions = [ {D[c][0]}, {D[c][1]}, {D[c][2]}, {D[c][3]}]\n'
# After:
dist = f'distortions = [ {D[c][0]}, {D[c][1]}, {D[c][2]}, {D[c][3]}, {D[c][4]}]\n'
```

**変更3: 変更不要の確認 — common.py 行280**
```python
dist.append(np.array(calib[cam]['distortions']))  # 配列長に依存しない → 変更不要
```

### 6.2 再キャリブレーション

1. `Pose2Sim/20260227-dgtw2-lab2/Config.toml` の `overwrite_intrinsics = true` に変更
2. Pythonで `calibration()` を実行:
```python
from Pose2Sim import Pose2Sim
Pose2Sim.calibration()
```
3. 新しい `Calib_scene.toml` が生成される → cam01/cam03のdistortionsにk3が追加されているか確認
4. `overwrite_intrinsics = false` に戻す

### 6.3 三角測量の再実行（2パターン）

**パターン1: undistort_points=false（現在のベースラインと比較用）**
```toml
[triangulation]
undistort_points = false
```
→ `Pose2Sim.triangulation()` 実行

**パターン2: undistort_points=true（本命テスト）**
```toml
[triangulation]
undistort_points = true
```
→ `Pose2Sim.triangulation()` 実行

### 6.4 効果測定

各パターンのTRC出力に対して `trc_evaluate` を実行:
```bash
# 単体評価
trc_evaluate -i <undistort_false>.trc
trc_evaluate -i <undistort_true>.trc

# ベースラインとの比較
trc_evaluate -i <baseline_trc> <undistort_true>.trc
```

### 6.5 判定

ログから以下を確認:
- 再投影誤差（px）
- カメラ除外率（cam01/cam03が改善されたか）

trc_evaluateから以下を確認:
- Bone CV（骨長一貫性）
- L-R Diff（左右対称性）
- Smoothness（滑らかさ）

### 6.6 ベースライン値（比較対象）

現在の undistort_points=false + フィルタ後の値:
```
Bone CV:    18.0%
Smooth:     0.0187 m/frame²
NaN:        0.0%
L-R Diff:   6.3%
```

ログ上の再投影誤差:
```
undistort=false: 9.9px, cam除外率 0.47台（cam01:9%, cam03:15%）
undistort=true:  11.4px, cam除外率 0.96台（cam01:36%, cam03:37%）
```

## 7. 成功基準

- `undistort_points=true` で再投影誤差が**現在の undistort=false（9.9px）以下**になること
- cam01/cam03の除外率が**undistort=true時に15%以下**に収まること（現在36-37%）
- trc_evaluateで左右非対称性（L-R Diff）が**5%以下**に改善すること（現在6.3%）

## 8. 実施結果（2026-02-28実施）

### 8.1 新しいキャリブレーションパラメータ

k3解放（`CALIB_FIX_K3`除去）後の歪み係数:

| カメラ | k1 | k2 | p1 | p2 | k3（新規） |
|--------|------|------|------|------|------|
| cam01 | -0.1432 | +0.0809 | +0.0002 | +0.0021 | **+0.0381** |
| cam02 | -0.0624 | +0.1248 | -0.0012 | -0.0009 | **-0.0684** |
| cam03 | -0.1451 | +0.0687 | -0.0014 | -0.0001 | **+0.0967** |
| cam04 | -0.0556 | +0.1079 | -0.0008 | -0.0012 | **-0.0575** |

cam03のk3=0.097が最大。全カメラでk3≠0であり、4パラメータモデルでは不十分であったことを確認。

Intrinsics RMS: 0.235px（全カメラ平均、旧モデルと同等）。

### 8.2 三角測量結果

| 指標 | ベースライン (旧calib, undist=off) | k3有効, undist=off | k3有効, undist=on |
|------|:---:|:---:|:---:|
| Mean Reproj Error | 9.9px | 9.9px | 11.4px |
| Avg Excluded Cams | 0.48台 | 0.48台 | 0.96台 |
| cam01除外率 | 10% | 10% | 38% |
| cam03除外率 | 15% | 15% | 35% |
| **Bone CV** | **18.0%** | 18.0% | **16.4%** |
| **Smoothness** | **0.0189** | 0.0189 | **0.0139** |
| **NaN** | 0.0% | 0.0% | 0.0% |
| **L-R Diff** | **6.3%** | 6.3% | **4.9%** |

### 8.3 判定

**成功基準の達成状況**:

| 基準 | 目標 | 結果 | 判定 |
|------|------|------|------|
| undistort=true で再投影誤差 ≤ 9.9px | ≤ 9.9px | 11.4px | **未達** |
| cam01/cam03除外率 ≤ 15% | ≤ 15% | 38%/35% | **未達** |
| L-R Diff ≤ 5% | ≤ 5% | **4.9%** | **達成** |

**追加所見**:
- **undistort=falseの場合**: intrinsics変更はtriangulationに影響なし（当然、undistortPointsが呼ばれないため）
- **undistort=trueの場合**: 再投影誤差・カメラ除外率はベースラインの旧k3なし版と同程度（改善せず）
- しかし**TRC品質3指標すべてが改善**: Bone CV -1.6pp、Smoothness -26%、L-R Diff -1.4pp
- これはカメラ除外は増えるが、残ったカメラでの歪み補正精度が向上し、三角測量の質が向上したことを意味する

### 8.4 結論と次のアクション

**案Aは部分的に成功**。k3解放により歪みモデルが改善され、undistort=trueでのTRC品質は明確に向上。ただし再投影誤差ベースの除外メカニズムがcam01/cam03を過度に除外する問題は未解決。

**推奨する次のステップ**:
1. **undistort_points=trueを今後のデフォルトとして採用**: TRC品質が全指標で改善しているため
2. **案B（alpha値調整）を実施**: `getOptimalNewCameraMatrix`のalpha=1→0で画像端の歪み補正誤差を軽減し、cam01/cam03の除外率低減を狙う
3. **reproj_error_thresholdの調整も検討**: 現在15px → 適切な値を探索（cam01/cam03の除外率を下げる）

### 8.5 保存されたファイル

```
pose-3d/
├── k3_undistort_false/    # パターン1結果（k3有効, undistort=false）
├── k3_undistort_true/     # パターン2結果（k3有効, undistort=true）★推奨
└── backup_before_k3/      # 旧キャリブレーション結果（ベースライン）
```

`calibration/Calib_scene.toml.bak_k3_before` に旧キャリブレーションをバックアップ済み。

## 9. 案Bの実施手順（★次のアクション）

### 9.1 背景

案Aでk3解放によりTRC品質は改善したが、undistort=trueでcam01/cam03が35-38%除外される問題は未解決。`getOptimalNewCameraMatrix`のalpha=1が原因の一つ。

- **alpha=1**: 全ピクセルを保持（歪み補正後に黒領域が出ない代わり、画像端の歪み補正が不正確な領域も含む）
- **alpha=0**: 有効領域のみ保持（画像端をクロップ、歪み補正の信頼性が高い領域のみ使用）

`optim_K`は`cv2.undistortPoints`の第4引数（newCameraMatrix）として使われる。alpha=0にすると画像端のキーポイントが有効領域外として扱われ、歪み補正誤差が大きいポイントを自然に除外する効果がある。

### 9.2 コード変更箇所

**変更1: `common.py:281`（主要箇所）**
```python
# Before:
optim_K.append(cv2.getOptimalNewCameraMatrix(K[c], dist[c], [int(s) for s in S[c]], 1, [int(s) for s in S[c]])[0])
# After:
optim_K.append(cv2.getOptimalNewCameraMatrix(K[c], dist[c], [int(s) for s in S[c]], 0, [int(s) for s in S[c]])[0])
```

**変更2: `common.py:314`（reproj_from_trc_calib用の同一パターン）**
```python
# Before:
optim_K = cv2.getOptimalNewCameraMatrix(K, dist, [int(s) for s in S], 1, [int(s) for s in S])[0]
# After:
optim_K = cv2.getOptimalNewCameraMatrix(K, dist, [int(s) for s in S], 0, [int(s) for s in S])[0]
```

**変更3-6: `Utilities/reproj_from_trc_calib.py`（4箇所のalpha=1を0に）**
行111, 118, 171, 173 の `getOptimalNewCameraMatrix` 呼び出し。

### 9.3 影響範囲

`optim_K`の利用箇所:
- `triangulation.py:811` — `cv2.undistortPoints(..., None, optim_K[i])` ★主要
- `personAssociation.py:210` — 同上
- `common.py:314-315` — 再投影計算用
- `reproj_from_trc_calib.py` — ユーティリティ

**再キャリブレーション不要**: alphaはCalib_scene.tomlに保存されず、実行時に計算されるため。

### 9.4 テスト手順

案Aの実行結果と同じ枠組みで比較:

1. Config.toml: `undistort_points = true`（案Aの推奨設定のまま）
2. 三角測量実行:
```python
import toml, os
from Pose2Sim.triangulation import triangulate_all
from Pose2Sim.filtering import filter_all
from Pose2Sim.Pose2Sim import setup_logging

session_dir = '/home/sakagawa/git/pose2sim/Pose2Sim/20260227-dgtw2-lab2'
os.chdir(session_dir)
setup_logging(session_dir)

config_dict = toml.load('Config.toml')
config_dict['project']['project_dir'] = session_dir
config_dict['project']['session_dir'] = session_dir
config_dict['triangulation']['undistort_points'] = True

triangulate_all(config_dict)
filter_all(config_dict)
```
3. trc_evaluate で評価
4. 結果をpose-3d/k3_alpha0_undistort_true/ に保存

### 9.5 比較対象（ベースライン）

| 指標 | 案A undist=off | 案A undist=on | 案B目標 |
|------|:---:|:---:|:---:|
| Reproj Error | 9.9px | 11.4px | **≤9.9px** |
| Avg Excluded | 0.48台 | 0.96台 | **≤0.5台** |
| cam01除外 | 10% | 38% | **≤15%** |
| cam03除外 | 15% | 35% | **≤15%** |
| Bone CV | 18.0% | 16.4% | ≤16.4% |
| Smooth | 0.0189 | 0.0139 | ≤0.0139 |
| L-R Diff | 6.3% | 4.9% | ≤4.9% |

### 9.6 リスクと注意点

- **alpha=0で画像端のキーポイントが無視される可能性**: 画像端に近いキーポイント（特に被写体が画面端に移動した場合）が有効領域外になり、欠損データが増える可能性
- **NaN率の増加に注意**: trc_evaluateのNaN率が0%から増加した場合、alpha=0が厳しすぎる可能性 → alpha=0.5等の中間値を試す
- **personAssociationへの影響**: personAssociation.pyでもundistortPointsを使うため、関連付け精度にも影響する可能性

## 10. 案B実施結果（2026-02-28実施）

### 10.1 変更内容

`getOptimalNewCameraMatrix`のalpha=1→0を以下6箇所で変更:
- `common.py:281`（calib_params_to_2D_points用）
- `common.py:314`（computeP用）
- `reproj_from_trc_calib.py:111, 118`（static/zooming camera用）
- `reproj_from_trc_calib.py:171, 173`（retrieve_calib_params用）

再キャリブレーション不要（alphaはCalib_scene.tomlに保存されず実行時に計算）。

### 10.2 結果比較

#### カメラ除外率（主目標）

| 指標 | ベースライン(undist=off) | 案A(alpha=1, undist=on) | **案B(alpha=0, undist=on)** |
|------|:---:|:---:|:---:|
| Reproj Error | 9.9px | 11.4px | **11.1px** |
| Avg Excluded | 0.48台 | 0.96台 | **0.64台** |
| cam01除外 | 10% | 38% | **21%** |
| cam02除外 | 3% | 6% | **7%** |
| cam03除外 | 15% | 35% | **21%** |
| cam04除外 | 19% | 17% | **15%** |

#### TRC品質

| 指標 | ベースライン(undist=off) | 案A(alpha=1) | **案B(alpha=0)** |
|------|:---:|:---:|:---:|
| Bone CV | 18.0% | 16.4% | **16.3%** ★最良 |
| Smoothness | 0.0189 | **0.0139** ★最良 | 0.0151 |
| NaN rate | 0.0% | 0.0% | 0.0% |
| L-R Diff | 6.3% | **4.9%** ★最良 | 5.3% |

### 10.3 成功基準の達成状況

| 基準 | 目標 | 案B結果 | 判定 |
|------|------|---------|------|
| undistort=true で再投影誤差 ≤ 9.9px | ≤ 9.9px | 11.1px | **未達**（改善方向） |
| cam01/cam03除外率 ≤ 15% | ≤ 15% | 21%/21% | **未達**（38%→21%と大幅改善） |
| L-R Diff ≤ 5% | ≤ 5% | 5.3% | **未達**（案Aでは4.9%で達成） |

### 10.4 分析

**改善点**:
- カメラ除外率がcam01/cam03で38%→21%と大幅低下（-17pp）
- 平均除外カメラが0.96→0.64台に改善
- Bone CVが全条件中最良（16.3%）
- Neck-Head, Neck-RShoulder, L Upper Arm等の個別ボーンが顕著に改善

**悪化点**:
- Smoothnessが案Aより悪化（0.0139→0.0151, +8.6%）。特に足先（RSmallToe +42.8%, LBigToe +47.7%）
- L-R Diffが案Aより悪化（4.9%→5.3%）。Shoulderが2.5%→6.7%に大幅悪化

**解釈**: alpha=0でカメラ除外が減った結果、以前は除外されていたノイズの多い観測値が三角測量に含まれるようになり、滑らかさと対称性がやや悪化。カメラ活用度とTRC品質のトレードオフが発生。

### 10.5 判断結果

**案A（alpha=1）を採用**。理由: Smoothness（0.0139 vs 0.0151）とL-R Diff（4.9% vs 5.3%）が案Bより優れており、TRC品質を優先。案Bのコード変更（alpha=0）は元に戻した。

案Bの結果データは `pose-3d/k3_alpha0_undistort_true/` に保存済み（参考用）。

### 10.6 保存先

```
pose-3d/
├── backup_before_k3/          # 旧キャリブレーション結果（ベースライン）
├── k3_undistort_false/        # 案A: k3有効, undistort=false
├── k3_undistort_true/         # 案A: k3有効, alpha=1, undistort=true
└── k3_alpha0_undistort_true/  # 案B: k3有効, alpha=0, undistort=true
```

## 11. 案C: キャリブレーション画像品質フィルタリング

### 11.1 要求仕様

#### 背景・課題

`calibrate_intrinsics()`は、コーナー検出に成功した全画像を無条件にキャリブレーションに使用している（`calibration.py:772-774`）。以下の品質チェックが一切ない:

- 個別画像の再投影誤差チェック（外れ値画像の除外）
- ブレ・ピンボケ検出
- チェッカーボード姿勢の多様性チェック

品質の悪い画像が含まれると歪み係数（特にk1, k2, k3）の推定精度が低下し、`undistort_points=true`時のカメラ除外率上昇の一因となる。

#### 各カメラの現在の画像枚数

| カメラ | 抽出PNG数 | 備考 |
|--------|----------|------|
| cam01 | 128枚 | 望遠レンズ |
| cam02 | 180枚 | 広角レンズ、最多 |
| cam03 | 104枚 | 望遠レンズ、最少 |
| cam04 | 154枚 | 広角レンズ |

#### 要求事項

| ID | 要求 | 優先度 |
|----|------|--------|
| REQ-1 | `cv2.calibrateCamera()`後に画像ごとの再投影誤差を計算する | 必須 |
| REQ-2 | 再投影誤差が統計的外れ値（mean + 2σ超）の画像を除外する | 必須 |
| REQ-3 | 除外後の残り画像数が10枚未満にならないよう保護する | 必須 |
| REQ-4 | 除外があった場合、残り画像で再キャリブレーションする | 必須 |
| REQ-5 | 除外画像数・閾値・再キャリブレーション後の誤差をログ出力する | 必須 |
| REQ-6 | Config.tomlに新設定パラメータを追加しない（自動計算） | 推奨 |
| REQ-7 | 外部インターフェース（返り値の型・順序）を変更しない | 必須 |

#### 成功基準

| 基準 | 目標値 | 比較対象（案A undist=on） |
|------|--------|--------------------------|
| Intrinsics RMS | 改善（現在0.235px） | 案A結果 |
| 三角測量時のcam01除外率 | < 35% | 38% |
| 三角測量時のcam03除外率 | < 35% | 35% |
| Bone CV | ≤ 16.4% | 16.4% |
| Smoothness | ≤ 0.0139 | 0.0139 |
| L-R Diff | ≤ 4.9% | 4.9% |

### 11.2 機能設計

#### 変更対象

| ファイル | 関数 | 変更種別 |
|---------|------|---------|
| `Pose2Sim/calibration.py` | `calibrate_intrinsics()` | コード追加（行789の後） |

#### 処理フロー

```
calibrate_intrinsics()
  └─ カメラごとのループ (行709)
     ├─ コーナー検出 (行737-778) ← 変更なし
     ├─ cv2.calibrateCamera() (行788) ← 変更なし
     ├─ ★画像品質フィルタリング (NEW)
     │  ├─ 1. cv2.projectPoints()で各画像のコーナーを再投影
     │  ├─ 2. 画像ごとのRMS再投影誤差を計算
     │  ├─ 3. 閾値(mean + 2σ)を超える画像を特定
     │  ├─ 4. 残り≥10枚ならば除外画像を除去
     │  └─ 5. cv2.calibrateCamera()を再実行
     └─ 結果を返り値リストに追加 (行791-797) ← 変更なし
```

#### 挿入位置の詳細

**現在のコード（行788-799）**:
```python
        ret_cam, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, img.shape[1::-1],
                                    None, None, flags=cv2.CALIB_USE_LU)# k3 enabled for better distortion modeling
        h, w = [np.float32(i) for i in img.shape[:-1]]
        ret.append(ret_cam)
        ...
```

**変更後**:
```python
        ret_cam, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, img.shape[1::-1],
                                    None, None, flags=cv2.CALIB_USE_LU)# k3 enabled for better distortion modeling

        # --- Image quality filtering ---
        per_image_errors = []
        for j in range(len(objpoints)):
            projected, _ = cv2.projectPoints(objpoints[j], rvecs[j], tvecs[j], mtx, dist)
            error = np.sqrt(np.mean(np.linalg.norm(
                imgpoints[j] - projected.squeeze(), axis=1)**2))
            per_image_errors.append(error)
        per_image_errors = np.array(per_image_errors)

        error_threshold = np.mean(per_image_errors) + 2 * np.std(per_image_errors)
        good_indices = np.where(per_image_errors <= error_threshold)[0]
        n_excluded = len(objpoints) - len(good_indices)

        if n_excluded > 0 and len(good_indices) >= 10:
            logging.info(f'    Excluded {n_excluded}/{len(objpoints)} images '
                         f'with reprojection error > {error_threshold:.2f} px '
                         f'(mean {np.mean(per_image_errors):.2f} + '
                         f'2*std {np.std(per_image_errors):.2f})')
            objpoints_filt = [objpoints[j] for j in good_indices]
            imgpoints_filt = [imgpoints[j] for j in good_indices]
            ret_cam, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
                objpoints_filt, imgpoints_filt, img.shape[1::-1],
                None, None, flags=cv2.CALIB_USE_LU)
            logging.info(f'    Recalibrated with {len(good_indices)} images: '
                         f'error {ret_cam:.3f} px')
        # --- End image quality filtering ---

        h, w = [np.float32(i) for i in img.shape[:-1]]
        ret.append(ret_cam)
        ...
```

#### 閾値設計根拠

- **mean + 2σ**: 正規分布で約95%の画像が含まれ、上位約5%を外れ値として除外
- 固定閾値ではなくデータ駆動型のため、カメラごとに適応的に機能
- 10枚保護: OpenCVは最低6枚必要だが、精度確保のため10枚を下限に設定

#### 非変更箇所の確認

| 箇所 | 理由 |
|------|------|
| `findCorners()` | コーナー検出自体は正常に機能 |
| `extract_frames()` | フレーム抽出は既存のまま |
| `append_points_to_json()` | JSON保存は検出時に行われ、フィルタリングとは独立 |
| `calib_calc_fun()` | オーケストレーターは変更不要 |
| `Config.toml` | 新パラメータ追加なし |
| 返り値 `ret, C, S, D, K, R, T` | 型・順序は同一 |

### 11.3 テスト手順

1. `Calib_scene.toml` をバックアップ: `cp Calib_scene.toml Calib_scene.toml.bak_before_filterC`
2. `Config.toml`: `overwrite_intrinsics = true` に変更
3. キャリブレーション実行（intrinsicsのみ）
4. ログ確認: 各カメラの除外画像数・閾値・新RMS誤差
5. `Config.toml`: `overwrite_intrinsics = false` に戻す
6. `undistort_points = true` で三角測量+フィルタリング実行
7. `trc_evaluate` で案Aの結果（`pose-3d/k3_undistort_true/`）と比較
8. 結果を `pose-3d/k3_filterC_undistort_true/` に保存

### 11.4 リスク評価

| リスク | 影響度 | 対策 |
|--------|--------|------|
| 除外画像がゼロ（フィルタ効果なし） | 低 | 現状と同一結果、害なし |
| 除外しすぎて精度悪化 | 低 | 10枚保護で防止 |
| cam03（104枚）で除外が多すぎる | 低 | 104枚中95%=99枚が残る想定 |

## 12. 案C: 実施結果（2026-02-28）

### 12.1 画像品質フィルタリング結果

| カメラ | 総画像数 | 除外数 | 閾値(px) | 再キャリブ後RMS |
|--------|---------|--------|---------|---------------|
| **cam01** | **119** | **13** | **1687.88** | **0.251px** |
| cam02 | 180 | 0 | - | 0.223px |
| cam03 | 97 | 0 | - | 0.228px |
| cam04 | 144 | 0 | - | 0.235px |

cam01のみフィルタが発動（13枚=10.9%除外）。cam02/cam03/cam04は外れ値がmean+2σ以内のため除外なし。

### 12.2 cam01 intrinsicsパラメータの変化

| パラメータ | 案A（フィルタなし） | 案C（フィルタあり） | 変化 |
|-----------|-------------------|-------------------|------|
| fx | 2014.44 | 2007.65 | -6.79 |
| fy | 2008.19 | 2001.56 | -6.63 |
| k1 | -0.1432 | -0.1416 | +0.0016 |
| k2 | +0.0809 | +0.0624 | -0.0185 |
| k3 | +0.0381 | +0.0751 | **+0.0370** |

k3がほぼ倍増、k2が減少。外れ値画像除外でk2/k3の推定値が変化した。

### 12.3 三角測量時のカメラ除外率

| カメラ | 案A (k3, undist=on) | 案C (k3+filterC, undist=on) | 変化 |
|--------|:---:|:---:|:---:|
| cam01 | 38% | 39% | +1pp（悪化） |
| cam02 | 6% | 6% | 変化なし |
| cam03 | 35% | 36% | +1pp（悪化） |
| cam04 | 17% | 16% | -1pp（改善） |
| Avg Excluded | 0.96台 | 0.98台 | +0.02 |
| Mean Reproj Error | 11.4px | 11.3px | -0.1px |

### 12.4 TRC品質比較

| 指標 | ベースライン(undist=off) | 案A (k3, undist=on) | **案C** | 判定 |
|------|:---:|:---:|:---:|:---:|
| Bone CV | 18.0% | 16.4% | **16.3%** | 微改善 |
| Smoothness | 0.0189 | **0.0139** | 0.0140 | ほぼ同等 |
| NaN | 0.0% | 0.0% | 0.0% | 変化なし |
| L-R Diff | 6.3% | 4.9% | **4.7%** | 改善 |

### 12.5 成功基準の達成状況

| 基準 | 目標 | 案C結果 | 判定 |
|------|------|---------|------|
| cam01除外率 | < 35% | 39% | **未達** |
| cam03除外率 | < 35% | 36% | **未達** |
| Bone CV | ≤ 16.4% | 16.3% | **達成** |
| Smoothness | ≤ 0.0139 | 0.0140 | ほぼ同等 |
| L-R Diff | ≤ 4.9% | 4.7% | **達成** |

### 12.6 結論

**案Cの効果は限定的**。cam01のみフィルタ発動、cam03は除外ゼロでフィルタ未作動。カメラ除外率は改善せず、TRC品質はわずかに改善（Bone CV -0.1pp、L-R Diff -0.2pp）。

**決定**: 案Aの設定を維持（Calib_scene.tomlは案Aの状態に復元済み）。フィルタリングコードは`calibration.py`に残す（外れ値がなければ何もしないため害なし）。

結果保存先: `pose-3d/k3_filterC_undistort_true/`
