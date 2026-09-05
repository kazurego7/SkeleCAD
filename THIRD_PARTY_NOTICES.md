# 配布物と外部依存

このリポジトリにはFreeCAD、Gmsh、CalculiX、Blender、OrcaSlicer、Bambu Studio、
Hunyuan3D、Python実行環境、AIモデル重みを同梱しません。
各依存はそれぞれの提供元の配布条件に従って別途導入してください。
`skelecad/config/toolchain.json`はローカルで検証した版・ハッシュの記録です。

`skelecad/assets/image_to_3d/`の入力画像と派生画像はローカル専用として除外します。
生成物、ユーザーのアップロード、ブラウザプロファイルも原則公開対象に含めません。
READMEの紹介用に選んだ画面キャプチャは `docs/media/` に同梱しています。
元画像・3Dモデルのソースデータは同梱していません。
これらを後から配布する場合は、個々の素材の出所と許諾条件を確認してください。

`skelecad/assets/workflow_tests/blue_robot.png`と`.blend`は、このプロジェクトの
`skelecad/tools/render_workflow_fixture.py`で構築した検証用シーンです。

リポジトリ独自のコードとドキュメントは [MITライセンス](LICENSE) です。
第三者ソフトウェア・AIモデル・画像の利用条件は、このMITライセンスで変更されません。
