# 環境構築・検証・公開

## 配布範囲

ソースと設定、手順書、自作のロボット検証用素材を配布します。
`.gitignore`で除外したファイルはローカルに残ります。
入力画像、過去の生成物、実行環境、ブラウザプロファイル、バックアップ、
アップロードした画像とジョブ履歴はGitに含めません。
既存ドキュメント中の`build/`へのリンクや検証結果は、製作者のローカル実行記録です。
新しいcloneの検証済み結果を意味しません。

## ソースのみで実行する検証

Python 3.14とNode.js 24（LTS）を用意し、ルートで実行します。

```powershell
python scripts/check_publication.py
node scripts/test_source.cjs
```

最初のコマンドはGitのインデックスを検査します。未ステージの変更は対象外です。
禁止フォルダ、認証情報の代表的な形式、個人パス、大きすぎるファイル、
PythonとJSONの構文を確認します。すべての秘密情報を検知するものではありません。
GitHub Actionsの`Source checks`もこの2つを実行します。

CPU上の画像・メッシュ処理テストは、別の仮想環境で実行できます。
依存の版はローカルのPython 3.14環境で取得したものです。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r skelecad/requirements-test.txt
Push-Location skelecad/tools
..\..\.venv\Scripts\python.exe -m unittest test_workflow test_workflow_geometry test_workflow_symmetry test_machine_image_job test_workflow_print test_workflow_print_release
Pop-Location
```

FreeCADを要するテスト、既存`build/`の全配信素材を要求する
`test_viewer_server.py`、入力画像・モデルが必要な`simple_viewer.test.cjs`は、
ソースのみの検証には含めません。製作環境では
`node --test skelecad/viewer/tests/*.test.cjs`でビュワーの全8ファイルを実行できます。

## 通常の起動：1コマンド

Windows x64で次のアプリを事前にインストールしてください。

- Bambu Studio（検証版02.08.02.61、A1 miniプリセットを使用）
- NVIDIA GPUドライバー（CUDA 13.2対応が必要）
- Microsoft Edge（Windows標準）

リポジトリを取得・展開したフォルダで実行します。

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

FreeCAD、uv、Python、CPU処理とCUDA推論のライブラリ、Hunyuanの形状生成ソースとモデルを自動で準備します。テクスチャ用のモデルは取得しません。管理者権限やPython・Git・uvの事前インストールは不要です。初回はネット接続・ダウンロード用の時間と空き容量が必要です。中断した場合は同じコマンドを再実行してください。

次回からは取得済み環境を再利用し、固定された依存との差分だけを同期します。Hunyuanモデルは既定のユーザーフォルダ`.cache/hy3dgen`、ソースと実行環境はリポジトリの`.tools/`に保存します。

画面を開かず準備だけ行う場合は `-SetupOnly`、サーバーだけ起動する場合は `-NoBrowser` を末尾に付けます。

### アプリのインストール先

FreeCADは`.tools/freecad-1.1.3/`へ自動取得します。Bambu Studioの既定位置は `C:/Program Files/Bambu Studio/` です。

別の場所の場合は、Git管理から除外される `skelecad/config/toolchain.local.json` に必要な項目だけ記入します。

```json
{
  "freecad": {
    "executable": "D:/Apps/FreeCAD/bin/freecad.exe",
    "python": "D:/Apps/FreeCAD/bin/python.exe"
  },
  "bambu_studio": {
    "executable": "D:/Apps/Bambu Studio/bambu-studio.exe",
    "library": "D:/Apps/Bambu Studio/BambuStudio.dll",
    "profiles": "D:/Apps/Bambu Studio/resources/profiles/BBL"
  }
}
```

### 外部依存と開発ツール

取得物にSkeleCADのMITライセンスを付与するものではありません。実行前に [外部依存の利用条件](../../THIRD_PARTY_NOTICES.md) を確認してください。
[uvの配布元](https://docs.astral.sh/uv/getting-started/installation/)・[Hunyuanの配布元](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1)

OrcaSlicerは不要です。実行環境とアーカイブ検査、旧Orca専用印刷経路を削除しました。
Blender・Gmsh・CalculiXは既存CADの画像生成・強度検証で使用している開発ツールです。通常の画像アップロードからプリント準備には不要で、自動取得しません。全ビルドを行う場合だけ `config/toolchain.json` の配置に用意してください。

## 既存製作モデルの全ビルド

`tools/build.ps1`は既存の恐竜の外観メッシュを入力に使います。
`build/generated_appearance/trex_appearance_200mm.stl`に加え、
`config/parameters.json`が参照する外観メッシュ・入力画像を別途復元する必要があります。
これらはGitには含めず、同じ見た目の完全再現はソースだけでは保証しません。

```powershell
.\skelecad\tools\build.ps1
```

この工程がツール整合性、CAD、STLの閉じた二多様体、3MF、組立衝突、
可動域、CalculiX解析を検査し、プレビューとレビュー束を再生成します。
形状や材質を変更した際は、この全検証が必要です。

## Gitへの公開

公開対象を確認してからコミットします。初期化済みのローカルリポジトリは`main`を使います。

```powershell
git add .
python scripts/check_publication.py
git diff --cached --stat
git diff --cached --check
git commit -m "Prepare SkeleCAD source distribution"
```

その後、利用するホスティング先で空のリポジトリを作り、そのURLを使って
`git remote add origin <URL>`、`git push -u origin main`を実行します。
この準備作業ではリモートの作成・登録や送信は行いません。
独自コードとドキュメントの利用条件は、ルートの [MITライセンス](../../LICENSE) を参照してください。

## FreeCADの自動準備

初回起動時に公式FreeCAD 1.1.3ポータブル版を取得し、`.tools/freecad-1.1.3`へ展開します。インストーラー・管理者権限・GUI操作は不要です。公式配布物のSHA-256を照合し、展開したPythonからFreeCAD・Part・Mesh・MeshPartの読み込みとソリッド生成を確認してから配置します。取得済みの実行環境は再利用します。

展開には自動取得した7-Zipのスタンドアロン展開ツールを使用します。FreeCADと展開ツールはGitへ含めません。
