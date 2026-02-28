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

## 6. 成功基準

- `undistort_points=true` で再投影誤差が**現在の undistort=false（9.9px）以下**になること
- cam01/cam03の除外率が**undistort=true時に15%以下**に収まること（現在36-37%）
- trc_evaluateで左右非対称性（L-R Diff）が**5%以下**に改善すること（現在6.3%）

## 7. 実施結果

（実施後にここに記録する）
