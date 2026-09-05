# 依存ライブラリ・ツール更新（2026-09-05）

## 採用した更新

| 対象 | 更新前 | 更新後 |
| --- | --- | --- |
| CPU処理用Python | 3.10.16（画像推論と共用） | 3.14.7（専用環境） |
| NumPy | 1.24.4 | 2.5.2 |
| SciPy | 1.14.1 | 1.18.1 |
| Trimesh | 4.4.7 | 5.1.0 |
| OpenCV | 4.10.0.84 | 5.0.0.93 |
| psutil | 6.0.0 | 7.2.2 |
| PyMeshLab | 2022.2.post3 | 2025.7.post1 |
| scikit-image | 0.24.0 | 0.26.0 |
| pygltflib | 1.16.3 | 1.16.5 |
| imageio | 2.36.0 | 2.37.4 |
| Gmsh | 4.15.0 | 4.15.2 |
| CalculiX | 2.22 | 2.23 |
| Blender | 4.5.11 LTS | 5.2.1 LTS |
| uv | 0.8.11 | 0.12.9 |
| GitHub Actions | checkout v4 / setup-python v5 / setup-node v4 | 各v7 |

CPU環境の全依存は`requirements-workflow.lock`に固定しています。
新環境は`.tools/python-runtime-3.14/`です。更新前の推論環境は上書きしていません。
FreeCAD同梱のPythonはCAD用として引き続き使用します。
CIはPython 3.14とNode.js 24 LTSを使います。ローカルのNode.js 26.8.1は公式の最新Current版と一致するため変更していません。

## 最新版を確認して据え置いたもの

- FreeCAD 1.1.3
- OrcaSlicer 2.4.2
- Bambu Studio 02.08.02.61
- Hunyuan3D 2.1ソース: `82920d643c0dc2f7bfd7255f45f62d386edfe60c`（取得元HEADと一致）
- Pillow 12.3.0、Manifold3D 3.5.2、Rtree 1.4.1

## 初回更新時の推論環境の保留（後続検証で解消）

以下は初回更新時点の判断です。その後、最新依存での実生成比較が成功したため、
推論環境も更新しました。現在の版と結果は[Hunyuan更新記録](HUNYUAN_UPDATE.md)を参照してください。

Hunyuan3Dの公式requirementsはPyTorch周辺とNumPyなどの旧版を前提にしています。
画像生成は従来のPython 3.10.16 / PyTorch 2.5.1+cu124 / torchvision 0.20.1+cu124、
transformers 4.46.0、diffusers 0.30.0、huggingface-hub 0.30.2を保持します。
推論の全依存を最新版にしたとは扱いません。

`workflow_worker.py`がこの専用環境の子プロセスで推論を行い、
背景処理・生成後の解析・関節加工・印刷準備は新しいCPU環境を使います。
現行GPUでのCUDA利用可能判定とHunyuanパイプラインのimportを確認しました。
AIモデル自体の変更や再学習は行っていません。

## 起動と説明の整備

起動・ビルド・スライスは`config/toolchain.json`からツールパスを選びます。
FreeCAD起動と全パーツ印刷配置は`palm_size.enabled`を反映します。
印刷アプリは`active_slicer`を反映し、比較キットは現行S3の選定元R3を開きます。
ビュワーの120 mm版表記を1.3.1に更新しました。
バージョン番号変更だけで既存の形状・材料を変更することはありません。

旧版3MFをテンプレートにする製作補助スクリプトは別の移行課題として残っています。
それらは外観や印刷方向を引き継ぐ処理であり、依存ライブラリの更新と同時に
印刷配置まで変更しないよう、今回はテンプレートの仕組みを置き換えていません。

## 取得元

- [FreeCAD公式リリース](https://github.com/FreeCAD/FreeCAD/releases/latest)
- [OrcaSlicer公式リリース](https://github.com/OrcaSlicer/OrcaSlicer/releases/latest)
- [Bambu Studio公式リリース](https://github.com/bambulab/BambuStudio/releases/latest)
- [Blender公式配布](https://download.blender.org/release/Blender5.2/)
- [Gmsh公式](https://gmsh.info/)
- [CalculiX公式](https://www.dhondt.de/)
- [uv公式リリース](https://github.com/astral-sh/uv/releases/latest)
- [Hunyuan3D公式依存](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/requirements.txt)
- Pythonパッケージ: PyPIの安定版メタデータから解決。

Blenderは配布元のSHA256と照合しました。Gmsh・CalculiXは公式ページにある
Windows配布を取得し、インストール後の実行ファイルSHA256を設定に固定しています。
旧アプリと更新前の依存一覧は`.tools/`内に保持しています。

## 検証結果

- 新CPU環境: 画像・メッシュ・印刷・STL処理74件合格。依存整合性検査も合格。
- FreeCAD呼び出しの設定参照化後、関節加工テスト19件を再実行して合格。
- ビュワー全8テストファイルとHTTP配信4テストが合格。
- Hunyuanパイプラインのimport、CUDA利用判定、新CPU環境からのGPU演算呼び出しが合格。
- 一括ビルドを実行し、CAD有効性、STL 23/23、3MF 26/26、組立衝突0件、
  可動域、基準・実骨・ボール軸・保持試験片のCalculiX解析が合格。
- 初回の描画でBlender 5系のEEVEE名称変更を検出。4つの描画スクリプトを互換化し、
  `--python-exit-code 1`で例外を失敗として伝えるよう修正。エラー終了コードも実測確認。
  描画・比較画像・レビュー束の工程を再実行し、画像の更新日時と見た目を確認。
- 実骨の20 N線形静解析: 最大変位0.627114 mm、最大von Mises応力12.841904 MPa。
  実物の嵌合・破壊・疲労試験の代わりにはなりません。
- ローカルサーバーをPython 3.14で再起動。既存ジョブの印刷準備完了状態を確認。
- 寸法・材料パラメータの変更はなし。Git公開は未実施。

一時的な実行記録`.runtime/upgrade-20260905/`と更新用フォルダ・旧Blenderは検証後にユーザーが削除しました。
検証レポートは`build/reports/`、再生成した画像は`build/preview/assembly.png`にあります。これらはGitには含めません。
GitHub Actionsは設定を更新しましたが、外部での実行はまだ行っていません。
画面を開いたままの場合は再読み込みして、新しいサーバーの操作トークンを取得してください。
