# 005: min_cameras_for_triangulation の最適化 [未着手]

## 現状

`min_cameras_for_triangulation = 2`

## やること

- [ ] 2台 vs 3台で比較テスト
- [ ] 3台にした場合の欠損フレーム数を確認
- [ ] 欠損部分のgap-filling戦略も合わせて検討

## トレードオフ

3台だと精度↑だが4台構成では欠損が増える可能性。

## 成功基準

再投影誤差の改善度合いと欠損率のバランス。
