# 003: undistort_points の再評価 [未着手]

**依存**: 002（intrinsicsキャリブレーション改善）の完了が前提

## 現状

`undistort_points = true` で再投影誤差が悪化（9.9px → 11.4px）、カメラ除外率が倍増。

## やること

- [ ] 002のキャリブレーション改善後に再テスト
- [ ] undistort_points = true/false で再投影誤差を比較
- [ ] カメラ別の除外率を確認

## 成功基準

undistort_points=true で精度向上、またはfalseが最適と確定。
