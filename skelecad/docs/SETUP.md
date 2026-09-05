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

## 製作環境

本番の起動・ビルドはWindows上の次の配置を前提にしています。
ツールは別途取得し、`config/toolchain.json`の版と整合させてください。

| リポジトリルートからの位置 | 内容 |
| --- | --- |
| `.tools/freecad-1.1.3/bin/` | FreeCAD 1.1.3と同梱Python、FreeCAD同梱ライブラリ |
| `.tools/blender-5.2.1-windows-x64/` | Blender 5.2.1 LTSのプレビュー生成環境 |
| `.tools/orcaslicer-2.4.2/` | OrcaSlicer 2.4.2 |
| `.tools/downloads/` | toolchain.jsonでハッシュ検査するOrcaSlicerアーカイブ |
| `.tools/hunyuan3d-2.1-modern-venv/` | Python 3.14.7、PyTorch 2.14/CUDA 13.2、更新済み推論依存 |
| `.tools/python-runtime-3.14/` | Python 3.14.7と`requirements-workflow.lock`のCPU依存 |
| `.tools/gmsh-4.15.2/` | Gmsh 4.15.2 |
| `.tools/calculix-2.23/` | CalculiX 2.23（ccx_static.exe） |
| `.tools/Hunyuan3D-2.1/` | Hunyuan3D 2.1ソース（`hy3dshape/`を含む） |
| `.tools/cache/huggingface/` | モデルキャッシュ |

Bambu Studioの既定位置は`C:/Program Files/Bambu Studio/`です。
実行ファイルとライブラリのハッシュ、プリセット名も`config/toolchain.json`に記録しています。
画像からの推論にはCUDA対応GPUと`tencent/Hunyuan3D-2.1`のモデルが必要です。
`requirements-test.txt`だけでは画像推論環境は完成しません。
CPU環境は更新済みのuvで、ルートから次のコマンドで再現できます。

```powershell
uv venv .tools/python-runtime-3.14 --python 3.14.7
uv pip sync --python .tools/python-runtime-3.14/Scripts/python.exe skelecad/requirements-workflow.lock
```

推論環境は[Hunyuan更新記録](HUNYUAN_UPDATE.md)の手順で再現できます。対応GPUドライバーと各外部アプリは別途導入してください。[更新記録](DEPENDENCY_UPDATE.md)に取得元を記載しています。

環境を用意したら、ルートで次を実行します。

```powershell
.\skelecad\tools\open_3d_viewer.ps1
```

入力をアップロードして新規ジョブを作成できます。既存モデルのメニューは
対応する生成物を置くまで利用できません。

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
オープンソースとして再利用を許可する場合は、所有者がライセンスを選び追加してください。
