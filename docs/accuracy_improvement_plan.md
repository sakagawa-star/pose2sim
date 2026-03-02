# 3Dキーポイント精度向上計画

## 概要

Pose2Simによる3D三角測量結果の精度を向上させるための改善ステップを管理する。
対象データセットは主に `20251127-dgtw-lab2` 系（4台カメラ、1920x1080）。

## ステップ一覧

| 管理番号 | カテゴリ | ステップ | 状態 | 優先度 | 詳細 |
|---------|---------|---------|------|--------|------|
| 000 | 設定検証 | Config.toml の正当性レビュー | **完了（検証済み）** | 最高 | [000_config_validation](000_config_validation/) |
| 001 | 設定修正 | handle_LR_swap を無効化 | 完了 | - | [001_disable_LR_swap](001_disable_LR_swap/) |
| 002 | キャリブレーション | intrinsicsキャリブレーションの改善 | **完了（案A採用・案B/C不採用）** | 高 | [002_improve_intrinsics_calibration](002_improve_intrinsics_calibration/) |
| 003 | 設定調整 | undistort_points の再評価 | **002結果により完了（undistort=true推奨）** | 高 | [003_reevaluate_undistort_points](003_reevaluate_undistort_points/) |
| 004 | 設定調整 | likelihood_threshold の最適化 | **事前調査完了・実施待ち** | 中 | [004_optimize_likelihood_threshold](004_optimize_likelihood_threshold/) |
| 005 | 設定調整 | min_cameras_for_triangulation の最適化 | **事前調査完了・実施待ち** | 中 | [005_optimize_min_cameras](005_optimize_min_cameras/) |
| 006 | 設定調整 | reproj_error_threshold の最適化 | **事前調査完了・実施待ち** | 中 | [006_optimize_reproj_error_threshold](006_optimize_reproj_error_threshold/) |
| 007 | 後処理 | fill_large_gaps_with 戦略の検討 | 未着手 | 低 | [007_fill_large_gaps_strategy](007_fill_large_gaps_strategy/) |
| 008 | 後処理 | フィルタリングパラメータの調整 | 未着手 | 低 | [008_optimize_filtering_parameters](008_optimize_filtering_parameters/) |
| 009 | 評価 | 定量的精度評価基盤の構築 | **完了** | 高 | [009_quantitative_accuracy_evaluation](009_quantitative_accuracy_evaluation/) |

---

## 進め方の方針

1. **009（評価基盤）を早期に着手** — 各改善の効果測定に必要
2. **002→003の順序は厳守** — キャリブレーション改善なしにundistort再評価は無意味
3. **004〜006は独立して並行可能** — それぞれ単独で試行できる
4. **各ステップの結果は各管理番号ディレクトリ内に記録** — 完了時に結果サマリを追記

## 変更履歴

| 日付 | 内容 |
|------|------|
| 2026-02-27 | 初版作成。既知の問題と対策をステップ化 |
| 2026-02-27 | 000追加。Config.tomlレビュー完了。undistort_points=true問題、パス不整合を検出 |
| 2026-02-28 | 管理番号を0詰め3桁に振り直し。各ステップを個別ディレクトリに分割 |
| 2026-02-28 | 000再調査完了。ログ未実装パラメータ、triangulation.py C3Dバグ、filtering make_c3d不足を修正 |
| 2026-02-28 | 009の調査・計画完了。trc_evaluate.py（4指標: 骨長CV/滑らかさ/欠損率/左右対称性）の実装設計を確定。実装待ち |
| 2026-02-28 | 009実装完了。trc_evaluate.py新規作成、pyproject.tomlにエントリーポイント追加。単体/比較/LSTM拡張TRC全テストパス。ベースライン計測済み |
| 2026-02-28 | 002コード調査完了。バグなし、設計上の制約3点を特定: (1)歪みモデル4パラメータ制限(CALIB_FIX_K3)、(2)alpha=1問題、(3)画像品質フィルタなし。改善案A-D策定済み |
| 2026-02-28 | 002の案A（k3解放）の実施手順を策定済み。次のセッションで実施開始 |
| 2026-02-28 | 002案A実施完了。k3解放→再キャリブレーション→三角測量2パターン(undist=off/on)実施。undist=onでTRC品質改善(BoneCV:18→16.4%, Smooth:-26%, L-R Diff:6.3→4.9%)。ただし再投影誤差・カメラ除外率は改善せず。undistort=true推奨、003も事実上完了 |
| 2026-02-28 | 002案B（alpha値調整）の実施手順を策定。common.py + reproj_from_trc_calib.pyのalpha=1→0変更。再キャリブレーション不要。次のセッションで実施開始 |
| 2026-02-28 | 002案B実施完了。alpha=1→0でcam01/cam03除外率38%→21%に大幅改善。ただしSmoothness・L-R Diffは案Aより悪化（トレードオフ）。**案A採用を決定、alpha=1に戻した** |
| 2026-02-28 | 002案C（画像品質フィルタリング）の要求仕様書・機能設計書を作成。計画承認済み、実施待ち |
| 2026-02-28 | 002案C実施完了。cam01のみ13/119枚除外、cam02-04は除外なし。TRC品質微改善（BoneCV:16.4→16.3%, L-R:4.9→4.7%）だがカメラ除外率は改善せず。**案A設定を維持**。コードは残置（害なし） |
| 2026-02-28 | **002クローズ**。案A-C全完了。案Aのk3解放のみ採用（BoneCV:18→16.4%, Smooth:-26%, L-R:6.3→4.9%）。cam除外率35-39%はキャリブレーション側では解決困難と結論 |
| 2026-03-02 | 004-006の事前調査完了。三角測量コードの処理フロー（likelihood→reproj_error→min_cameras）を解明。各README.mdにテスト条件・予想結果・成功基準を記載。推奨実施順: 006(12px)→004(0.3)→005(3台) |
