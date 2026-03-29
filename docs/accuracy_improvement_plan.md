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
| 004 | 設定調整 | likelihood_threshold の最適化 | **凍結（カメラ再配置待ち）** | - | [004_optimize_likelihood_threshold](004_optimize_likelihood_threshold/) |
| 005 | 設定調整 | min_cameras_for_triangulation の最適化 | **凍結（カメラ再配置待ち）** | - | [005_optimize_min_cameras](005_optimize_min_cameras/) |
| 006 | 設定調整 | reproj_error_threshold の最適化 | **凍結（カメラ再配置待ち）** | - | [006_optimize_reproj_error_threshold](006_optimize_reproj_error_threshold/) |
| 007 | 後処理 | fill_large_gaps_with 戦略の検討 | **完了（nan推奨）** | 低 | [007_fill_large_gaps_strategy](007_fill_large_gaps_strategy/) |
| 008 | 後処理 | フィルタリングパラメータの調整 | **完了（kalman tr=100推奨）** | 低 | [008_optimize_filtering_parameters](008_optimize_filtering_parameters/) |
| 009 | 評価 | 定量的精度評価基盤の構築 | **完了** | 高 | [009_quantitative_accuracy_evaluation](009_quantitative_accuracy_evaluation/) |
| 010 | 調査 | 2Dキーポイント信頼度分析 | **完了（カメラ配置問題を特定）** | 高 | [010_2d_confidence_analysis](010_2d_confidence_analysis/) |
| 011 | 調査 | バウンディングボックスIDスイッチ問題 | **Phase 1実装完了・分析結果取得済み** | 高 | [011_id_switch_analysis](011_id_switch_analysis/) |
| 012 | 調査 | 2Dキーポイント推定の暴れ対策 | **Phase 1実装完了・分析済み・調査停止中** | 高 | [012_2d_keypoint_jitter](012_2d_keypoint_jitter/) |
| 013 | 調査 | 頭部キーポイント精度向上 | **Phase 1レビュー通過・実装待ち** | 中 | [013_head_keypoint_accuracy](013_head_keypoint_accuracy/) |
| 014 | ツール | 主要人物抽出CLIツール | **機能設計書作成待ち** | 高 | [014_pose_extract_person](014_pose_extract_person/) |
| 015 | 不具合修正 | Kalmanフィルタ短シーケンスクラッシュ | **完了** | 高 | [015_filtering_short_sequence](015_filtering_short_sequence/) |
| 016 | ツール | 2Dキーポイントオーバーレイ動画生成 | **完了** | 中 | [016_pose_overlay_video](016_pose_overlay_video/) |
| 017 | ツール | キーポイント信頼度タイムライン | **完了** | 中 | [017_confidence_timeline](017_confidence_timeline/) |
| 018 | ツール | オーバーレイ動画confidence閾値フィルタ | **完了** | 中 | [018_overlay_confidence_filter](018_overlay_confidence_filter/) |
| 019 | ツール | オーバーレイ動画MP4背景対応 | **要求仕様書・機能設計書作成待ち** | 中 | [019_overlay_video_background](019_overlay_video_background/) |

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
| 2026-03-02 | 010追加。2Dキーポイント信頼度の精査。三角測量の前提データ品質を調査 |
| 2026-03-02 | 010分析完了。左側キーポイント（LWrist/LElbow/LHip）が系統的に低信頼度。カメラの片側半円配置による死角（左半身の自己遮蔽）が原因と判明 |
| 2026-03-02 | **004-006を凍結**。カメラ配置の構造的制約により、現データでのパラメータ最適化は精度改善が期待できない。カメラ再配置後の新映像データで再開予定 |
| 2026-03-02 | 007調査・比較テスト完了。5/26マーカーに大ギャップ存在（0.55%）。nan戦略がlast_valueより全指標改善（BoneCV:16.3→15.4%, L-R:4.7→4.1%）。last_valueは最大570mmテレポートジャンプ生成 |
| 2026-03-02 | **007クローズ**。nan採用、Config.toml適用済み。zeros はnanの下位互換（不採用）。ギャップ部分のLSTM出力はどの戦略でも信頼できない |
| 2026-03-02 | 008開始。nan設定でパイプライン再実行済み、ベースライン確定（BoneCV:15.4%, Smooth:0.0139, L-R:4.1%）。6種フィルタ比較→パラメータスイープの計画で実施中 |
| 2026-03-02 | **008クローズ**。6種フィルタ×デフォルトパラメータ比較→上位2種(kalman/one_euro)パラメータスイープ→reject_outliers検証。kalman tr=100推奨（Smooth -68%, BoneCV -0.8pt, L-R +0.3pt）。one_euro beta=1はBoneCV/Smooth最良だがL-R +1.0pt悪化 |
| 2026-03-04 | 011/012/013追加。2D品質改善の3課題（IDスイッチ/キーポイント暴れ/頭部精度）。各Phase 1の要求仕様書・機能設計書を作成。011は20251024_osaka-hosp.PortalCam.01hourで調査（3カメラ、10.8万フレーム、常時3人検出）。012/013は20260227-dgtw2-lab2を主対象 |
| 2026-03-05 | 011/012/013の要求仕様書・機能設計書がSubagentレビュー通過。013でキーポイントインデックスの致命的誤り（TRC列順とJSON配列順の混同）を検出・修正。全3件Phase 1実装待ち |
| 2026-03-05 | 011 Phase 1実装完了。id_switch_analyze.py新規作成。10.8万フレーム×3カメラを25秒で処理。検出人数分布は事前調査と一致。マッチング距離: cam01中央値16.3px, cam02=10.8px, cam04=33.8px。パターンC（一時的人数増減反転）が最多 |
| 2026-03-10 | 012 Phase 1実装完了。keypoint_jitter_analyze.py新規作成。6,627件の暴れイベント検出。パターンE(その他)が68.7%で全カメラ共通→RTMpose推定の揺らぎが主因。足先は障害物遮蔽（想定通り）。上半身はLWrist(272件)とHead/Ear(191-228件)がやや多い。動画確認未実施のため**調査停止** |
| 2026-03-13 | 012改修: _select_person()追加（複数人フレーム対応）、ディレクトリ名パターン拡張。20150910_osaka_hospデータ(97,425フレーム)で暴れ分析実行。パターンD(低conf)66.2%が主因。患者抽出をワンショット実行済み |
| 2026-03-13 | 014追加。主要人物抽出CLIツール(pose_extract_person)。複数人検出フレームから主要人物のみを抽出。機能設計書作成待ち |
| 2026-03-23 | 015追加。filtering.pyのkalman_filter_1dで有効データ2〜3フレームのシーケンスがIndexErrorを起こす不具合。20260319-dgtw-labデータ（人が一時的に消える区間あり）で発生。修正: 最低シーケンス長を2→4に変更 |
| 2026-03-23 | **015クローズ**。kalman_filter_1dの最低シーケンス長を2→4に修正。20260319-dgtw-lab2データでfiltering()が正常完了することを確認 |
| 2026-03-25 | 016追加。2Dキーポイントオーバーレイ動画生成ツール（pose_overlay_video）。背景画像+JSON→キーポイント描画動画。要求仕様書・機能設計書作成、レビュー通過 |
| 2026-03-26 | **016クローズ**。pose_overlay_video実装完了。実機確認OK |
| 2026-03-26 | 017追加。キーポイント信頼度タイムラインCLIツール（confidence_timeline）。フレーム単位の信頼度散布図+CSV出力。人物インデックス色分け対応 |
| 2026-03-26 | **017クローズ**。confidence_timeline実装完了。実機確認OK |
| 2026-03-29 | 018/019追加。pose_overlay_videoの機能拡張2件（confidence閾値フィルタ/MP4動画背景対応）を分離発番 |
| 2026-03-29 | **018クローズ**。pose_overlay_videoに-c/--conf_threshold引数を追加。閾値未満のキーポイント・骨格線を非表示化。実機確認OK |
