# 同じPLAで印刷するジョイントの表面対策

ボールを上向きにすると棒が折れやすくなるというユーザーの実機経験を優先し、
上向き優先の自動配置変更は撤回した。画像ワークフローの配置は従来の
最低高さ優先へ戻し、既存の固定配置プレートも維持する。

## サポート接触面の試験設定

| 設定 | 従来 | 新設定 |
| --- | --- | --- |
| サポート上部隙間 | 0.24 mm | 0.20 mm |
| 上部接触層 | 2層 | 3層 |
| 接触層の線間隔 | 0.50 mm（プリセット継承） | 0.20 mm |
| 接触層の速度 | 80 mm/s（プリセット継承） | 35 mm/s |

接触層を密に、低速で作り、サポート上の垂れを抑えることを狙う。
同材PLAでの物理的な改善は未検証。隙間を縮めると剥がしにくくなる場合がある。
まず少量で表面・除去性・嵌合を確認し、剥離時に傷む場合は上部隙間を0.24 mmへ
戻して比較する。球径や受け径を変えてサポート跡を補償しない。

本体積層0.16 mm、4壁、サポートXY距離0.45 mm、tree(auto)、PLA Matte、
選択済みS3の球径6 mm・受け径5.90 mmは維持。
設定はconfig/parameters.jsonのprinting.support_defaultsで管理し、
Bambuの新規印刷準備と出力監査に反映する。既存3MF・G-codeは自動更新しない。

## 検証

加工済みプテラノドン7部品でBambu Studioの検証用スライスに成功。
旧input.3mfとの全7部品の変換行列・配置は完全一致。
元メッシュ一致、3MF構造、新設定の保持、全7部品の出力、サポート生成、
サポート込みの180 mmベッド範囲、G-code整合性の監査を通過した。
見積もり5310秒（1時間28分30秒）、14.86 g。プリンターへの送信は行っていない。
通常タイムラプス非対応の通知以外にスライサー警告なし。

検証結果: skelecad/.runtime/joint-support-settings/print/release.json
試験3MF: skelecad/.runtime/joint-support-settings/print/plate_01/SkeleCAD_A1mini_plate_01.3mf
画像ワークフローの印刷・公開ゲート関連テスト17件成功。
CAD形状・材料・組立は変更していないため、CAD再生成・衝突解析・CalculiXは
今回再実行していない。嵌合・棒の強度・接触面改善は実機確認待ち。

参考: [Bambu Studio公式の設定定義](https://github.com/bambulab/BambuStudio/blob/master/src/libslic3r/PrintConfig.cpp)
（support_interface_spacing / support_interface_top_layers / support_interface_speed）。
新しい数値はこのプロジェクトの試験値であり、メーカー保証値ではない。
