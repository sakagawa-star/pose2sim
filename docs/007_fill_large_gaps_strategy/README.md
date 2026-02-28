# 007: fill_large_gaps_with 戦略の検討 [未着手]

## 現状

`fill_large_gaps_with = "last_value"`

## 選択肢

`"last_value"`, `"nan"`, `"zeros"`

## やること

- [ ] 各戦略での3D軌跡の連続性を確認
- [ ] 後段処理（フィルタリング、LSTM）への影響を評価

## 成功基準

後処理に悪影響を与えない補間戦略を選択。
