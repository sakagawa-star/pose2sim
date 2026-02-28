# 006: reproj_error_threshold の最適化 [未着手]

## 現状

`reproj_error_threshold_triangulation = 15.0`

## やること

- [ ] 10, 12, 15, 20 で比較テスト
- [ ] しきい値ごとの除外率と3D精度を評価

## 成功基準

外れ値を除外しつつ有効データを最大限残す閾値を特定。
