# ライセンス・クレジット

## SkeleCAD

独自コードとドキュメントは [MITライセンス](LICENSE) です。
著作権表記：Copyright (c) 2026 kazurego7

## Hunyuan3D 2.1

SkeleCADは、画像から3Dモデルを生成する機能に、Tencentが公開する
[Hunyuan3D 2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1)を使用しています。
紹介画面の3D形状も、AIによる生成後にパーツ分割・ジョイント加工を行ったものです。

**SkeleCADはTencentと提携・関連しておらず、Tencentによる後援・公認・推奨を受けていません。**

- [Tencent Hunyuan 3D 2.1 Community License Agreement 全文](licenses/Hunyuan3D-2.1-LICENSE.txt)
- [指定の著作権・商標表記（NOTICE）](NOTICE)
- [公式のライセンス](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE)

同梱したライセンス本文は2026年9月5日に公式リポジトリから取得した原文です。

## 配布物と外部依存

このリポジトリにはFreeCAD、Gmsh、CalculiX、Blender、Bambu Studio、
Hunyuan3D、Python実行環境、AIモデル重みを同梱しません。
FreeCADは初回起動時に公式ポータブル版を取得します。Bambu Studioは利用者がインストールします。
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

## 自動セットアップの取得物

`start.ps1`は利用者のPCで公式配布元からFreeCADポータブル版・展開ツール・実行環境・依存ライブラリ・Hunyuanのソースと形状モデルを取得します。この準備処理はSkeleCAD独自コードのMIT表記を変更しませんが、取得物をMITに再ライセンスするものでもありません。

- FreeCAD：公式ポータブル配布物内のライセンス・著作権表示を保持します。[公式ライセンス](https://github.com/FreeCAD/FreeCAD/blob/main/LICENSE)
- 7-Zip：展開用の`7zr.exe`を利用します。[公式サイト](https://www.7-zip.org/)
- uv：MIT / Apache-2.0。[公式ライセンス](https://github.com/astral-sh/uv/blob/main/LICENSE-MIT)
- Hunyuan3D 2.1：Tencent Hunyuan 3D 2.1 Community License Agreement。EU・英国・韓国を除く地域に限定され、用途・生成物の利用・配布・一定規模の商用利用などに条件があります。[公式規約全文](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE)
- PyMeshLab：GPLv3。Hunyuanの上流パッケージが読み込む依存です。独自コードのMIT表記は、GPL対象物を含む統合物・実行環境の再配布条件を保証しません。[公式ライセンス](https://github.com/cnr-isti-vclab/PyMeshLab/blob/main/LICENSE)
- その他のPythonライブラリと外部アプリにも、それぞれのライセンスが適用されます。各取得物に含まれるライセンス・著作権表示を保持してください。

公開するのは独自ソースと設定です。`.tools/`やモデル重みを含むインストール済み環境を、そのままMITの配布物として公開しないでください。Hunyuanを利用する製品・サービスの配布には、規約の提供や実際の提供主体の表示など、別途満たす条件があります。SkeleCADはTencentの公式製品ではなく、提携・後援・推奨を受けていることを示すものではありません。
