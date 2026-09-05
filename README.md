# SkeleCAD

FreeCADで精密な関節を作り、画像由来の3Dモデルを分割・組立・検証して、
3Dプリント用データを準備するWindows向けの試作プロジェクトです。
ブラウザでモデルの回転、関節操作、衝突確認、画像処理ジョブの管理を行います。

現在の製作設定はrevision 1.3.1、全長120 mm、6 mmボールのjoint-v3です。
寸法と材料の正本は [parameters.json](skelecad/config/parameters.json) です。

## はじめに

このリポジトリは**ソース配布**です。アプリ本体、AIモデルの重み、入力画像、
生成済みCAD/STL/3MF、個人の作業履歴は含みません。
cloneだけでは既存の恐竜モデルの表示や全工程の再生成はできません。

- [環境構築・テスト・公開手順](skelecad/docs/SETUP.md)
- [プロジェクトの操作説明](skelecad/README.md)
- [設計と検証上の制約](skelecad/docs/DESIGN.md)
- [変更履歴](skelecad/docs/CHANGELOG.md)
- [配布物と外部依存について](THIRD_PARTY_NOTICES.md)

## ソースの検証

リポジトリのルートでPython 3.14とNode.js 24（LTS）を使用します。

```powershell
python scripts/check_publication.py
node scripts/test_source.cjs
```

GitHub Actionsでも公開対象の検査とビュワーのテストを実行します。
CAD・STL・衝突・CalculiXの検証は、必要なツールと入力を用意した環境で
`skelecad/tools/build.ps1`を実行する別工程です。

## 構成

| 場所 | 内容 |
| --- | --- |
| `skelecad/src/` | CAD生成、メッシュ処理、検証・CAE |
| `skelecad/tools/` | 起動、画像ワークフロー、印刷準備、テスト |
| `skelecad/viewer/` | ローカルWebビュワー |
| `skelecad/config/` | 寸法・材料、ツールのバージョンとハッシュ |
| `skelecad/docs/` | 設計、操作、過去の検証記録 |
| `skelecad/assets/workflow_tests/` | 自作のロボット検証用素材 |

`legacy_prototypes/`はローカルの参照用に保持し、Git管理から除外しています。
本プロジェクトは試作品であり、CAE結果だけで実物の嵌合・耐久性を保証しません。

## ライセンス

現時点ではオープンソースライセンスを付与していません。
利用・再配布の許諾条件は所有者が別途決定します。
