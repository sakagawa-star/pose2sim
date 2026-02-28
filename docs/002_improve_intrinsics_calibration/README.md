# 002: intrinsicsキャリブレーションの改善 [調査完了・実施待ち]

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
