# 012 Phase 1 分析結果: 2Dキーポイント暴れ分析

## 1. データ概要

- cam01: 1800 frames
- cam02: 1794 frames
- cam03: 1799 frames
- cam04: 1794 frames
- キーポイント数: 26 (HALPE_26)
- 暴れ閾値倍率: 5.0

## 2. 分析結果サマリ

暴れ検出イベント合計: **6627**

```
=== 2D Keypoint Jitter Analysis ===
Cameras: 4 (cam01, cam02, cam03, cam04)
Total frames: 7187
Jitter threshold multiplier: 5.0

--- Jitter Count per Camera x Keypoint ---
Keypoint         cam01   cam02   cam03   cam04   total
------------------------------------------------------
Nose                11      21      30      52     114
LEye                20      14      45      47     126
REye                13      20      33      51     117
LEar                39      22      64     103     228
REar                31       6      53      69     159
LShoulder           16      16      34      52     118
RShoulder            3       8      14      50      75
LElbow              36      20      34      50     140
RElbow               8      23      10      36      77
LWrist              78      43      81      70     272
RWrist              21      36      22      38     117
LHip                 7      10      31      28      76
RHip                 6       7      18      24      55
LKnee               41      34      67      56     198
RKnee               31      30      35      50     146
LAnkle              90      89     101     125     405
RAnkle             147     146     144     143     580
Head                31      19      71      70     191
Neck                19       7      38      75     139
Hip                  3       8       5      18      34
LBigToe            112     107     127     149     495
RBigToe            149     162     192     186     689
LSmallToe          107     114     108     137     466
RSmallToe          154     154     183     197     688
LHeel               96      95      95     115     401
RHeel              127     135     129     130     521
TOTAL             1396    1346    1764    2121    6627

--- Pattern Distribution ---
  A (Out-of-frame): 2059 (31.1%)
  C (Small BB): 12 (0.2%)
  D (Low confidence): 4 (0.1%)
  E (Other): 4552 (68.7%)
  Total: 6627

--- Top 5 Problematic Keypoints ---
  RBigToe        total=689  (cam01=149  cam02=162  cam03=192  cam04=186)
  RSmallToe      total=688  (cam01=154  cam02=154  cam03=183  cam04=197)
  RAnkle         total=580  (cam01=147  cam02=146  cam03=144  cam04=143)
  RHeel          total=521  (cam01=127  cam02=135  cam03=129  cam04=130)
  LBigToe        total=495  (cam01=112  cam02=107  cam03=127  cam04=149)

--- Median Displacement & Threshold (px) ---
Keypoint       cam01-med cam01-thr cam02-med cam02-thr cam03-med cam03-thr cam04-med cam04-thr
----------------------------------------------------------------------------------------------
Nose                 2.8      14.1       2.3      11.4       3.3      16.7       3.7      18.5
LEye                 2.6      13.0       2.2      10.9       3.1      15.5       3.6      17.8
REye                 2.7      13.6       2.2      11.0       3.2      15.9       3.6      18.0
LEar                 2.4      12.1       2.0      10.1       3.0      14.8       3.3      16.4
REar                 2.4      12.1       2.2      10.9       2.9      14.3       3.2      15.9
LShoulder            2.4      12.1       1.9       9.3       3.0      14.9       3.0      14.8
RShoulder            2.8      14.1       2.2      11.0       3.4      17.2       3.3      16.4
LElbow               2.8      14.0       2.1      10.4       3.5      17.6       3.3      16.4
RElbow               3.1      15.3       2.4      11.8       3.6      18.2       3.6      17.8
LWrist               3.1      15.6       2.6      12.8       4.1      20.3       3.5      17.4
RWrist               3.1      15.5       2.4      12.1       3.7      18.7       3.7      18.3
LHip                 2.8      13.8       2.0      10.2       3.5      17.5       2.9      14.7
RHip                 2.6      13.0       2.0      10.2       3.3      16.6       2.9      14.7
LKnee                2.3      11.5       1.8       9.1       2.7      13.4       2.5      12.4
RKnee                2.3      11.5       1.8       9.2       2.8      14.1       2.7      13.5
LAnkle               2.0      10.1       1.6       7.8       2.3      11.4       1.9       9.5
RAnkle               1.8       8.8       1.3       6.7       2.3      11.3       2.0      10.2
Head                 2.4      12.0       2.0       9.9       3.0      14.8       3.3      16.7
Neck                 2.2      11.2       1.8       8.9       2.9      14.5       2.7      13.3
Hip                  2.2      11.2       1.7       8.7       2.7      13.7       2.6      13.2
LBigToe              2.2      10.8       1.8       9.0       2.5      12.5       2.1      10.4
RBigToe              2.1      10.4       1.5       7.4       2.6      13.0       2.1      10.6
LSmallToe            2.2      10.8       1.8       9.0       2.4      12.2       2.0      10.2
RSmallToe            2.0      10.1       1.6       8.2       2.6      13.0       2.0      10.1
LHeel                2.0      10.2       1.7       8.5       2.4      12.2       2.2      11.0
RHeel                2.0      10.2       1.5       7.5       2.4      12.1       2.3      11.4

```

## 3. プロット画像

- `test_results/jitter_heatmap.png`: カメラ×キーポイント暴れ頻度ヒートマップ
- `test_results/jitter_confidence_dist.png`: 暴れ時 vs 通常時のconfidence分布
- `test_results/jitter_pattern_dist.png`: 原因パターン別分布
- `test_results/jitter_timeseries_top3.png`: 暴れ上位3キーポイントの移動量時系列

## 4. カメラ別パターン分布

| カメラ | A (画面外) | C (小BB) | D (低conf) | E (その他) | E率 |
|--------|-----------|---------|-----------|-----------|-----|
| cam01 | 237 | 0 | 0 | 1,159 | 83% |
| cam02 | 204 | 0 | 0 | 1,142 | 85% |
| cam03 | 888 | 12 | 0 | 864 | 49% |
| cam04 | 730 | 0 | 4 | 1,387 | 65% |

パターンEは全カメラで発生（カメラ配置に依存しない）。cam03はパターンA(画面外)が多く、被写者が画面端に近い配置と推測。

## 5. パターンE多発フレーム（動画確認用）

パターンEが集中する（複数KPが同時に暴れる）フレーム帯:

### フレーム 982〜993（約32.7〜33.1秒）— 全カメラ共通、最も顕著
- 暴れKP: Nose, LEye, REye, LEar, REar, LShoulder, RShoulder, Head, Neck
- **頭部〜肩が一斉に暴れる**。全カメラで同時発生 → 被写者の急な動き（振り向き等）が原因の可能性
- cam03: フレーム985-992で毎フレーム8-9KP同時暴れ
- cam04: フレーム985-990で毎フレーム10KP同時暴れ

### フレーム 925〜935（約30.8〜31.2秒）— cam04中心
- cam04フレーム935: **12KP同時暴れ**（全データ中最大）
- Nose, LEye, REye, LEar, REar, LShoulder, RShoulder, LElbow, LHip, RHip, Head, Neck
- 上半身全体が一斉に動いている

### フレーム 996〜1002（約33.2〜33.4秒）— cam01中心
- 左半身が集中: LEar, LShoulder, LElbow, LWrist, LHip, LAnkle, LBigToe, LSmallToe, LHeel
- 体の向き変化で左側の見え方が急変した可能性

### フレーム 1020〜1025（約34.0〜34.2秒）— cam02中心
- 右半身が集中: RElbow, RWrist, RKnee, RAnkle, RBigToe, RSmallToe, RHeel

## 6. 考察

### 足先の暴れ（想定通り）
- RBigToe(689), RSmallToe(688), RAnkle(580), RHeel(521), LBigToe(495) が上位を占める
- **障害物による遮蔽が原因**（ユーザー確認済み）。撮影環境の制約であり、ソフトウェア対策は困難

### 上半身の暴れ（軽微だが注目点あり）
- 体幹（Hip/Neck/Shoulder）は安定（暴れ率0.5〜1.9%）
- **LWristが上半身で突出**（272件、RWristの2.3倍）— cam01=78, cam03=81で多い
- **頭部周辺（Head/LEar/REar）もやや多め**（191〜228件）— cam04でLEar=103が特に多い

### パターンEの主因
- 全暴れの68.7%がパターンE（confidence高・BB正常なのに暴れる）
- 全カメラで共通して発生 → カメラ配置ではなく**RTMpose推定自体の揺らぎ**が主因
- フレーム982〜993の集中暴れは被写者の急動作に起因する可能性 → **動画確認で要検証**

### 調査停止時点の状態（2026-03-10）
- Phase 1: 実装・実行・初期分析完了
- **動画確認が未実施**（フレーム985/935/1000/1020付近）
- Phase 2（RTMpose設定調査）・Phase 3（閾値最適化）: 未着手
