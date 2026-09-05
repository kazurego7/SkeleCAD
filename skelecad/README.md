# SkeleCAD

画像から3D形状を生成し、分割位置の指定、関節加工、可動確認、Bambu用印刷データの
準備までを行うローカルアプリです。Windowsで動作します。
初回は[環境構築](docs/SETUP.md)を参照してください。

## 現在の構成

- ビュワー・画像処理・メッシュ加工: Python 3.14.7と更新済みのCPUライブラリ。
- 画像推論: Hunyuan3D 2.1、Python 3.14.7 / PyTorch 2.14 / CUDA 13.2。
- CAD: FreeCAD 1.1.3。解析: Gmsh 4.15.2 / CalculiX 2.23。
- 描画: Blender 5.2.1 LTS。標準スライサー: Bambu Studio 02.08.02.61。
- 既存製作モデル: revision 1.3.1、全長120 mm、S3保持具合を採用したjoint-v3。

ツールのパスとハッシュは`config/toolchain.json`、寸法・材料は
`config/parameters.json`で管理します。[更新記録](docs/DEPENDENCY_UPDATE.md)と[Hunyuanの追加検証](docs/HUNYUAN_UPDATE.md)も参照してください。

## 起動

リポジトリのルートで実行します。

```powershell
.\skelecad\tools\open_3d_viewer.ps1
```

画像を画面にドロップして生成を開始します。分割位置の調整、左右対称化、
ジョイント加工を行い、動かして確認した姿勢で「プリント準備」を進めます。
「プリント」は準備済みデータをBambu Studioで開きます。プリンターへの送信は行いません。
元画像、生成物、ジョブ履歴は`build/workflows/`に保存され、Gitには含まれません。

## 操作

- パーツを中央付近からドラッグすると曲げ、外側で円を描くかShiftを押すとねじります。
- 背景のドラッグで視点を回転、中ボタンドラッグで平行移動、ホイールで拡大縮小します。
- Homeで選択関節、Escで全関節を元に戻します。
- 保存した姿勢・視点のスナップショットは同じブラウザに残ります。他端末とは同期しません。
- モデル一覧には生成したモデルとゴミ箱があります。

赤い点はサンプルによる食い込み検出です。連続した可動域や実物の強度を保証しません。
新規画像のジョイント加工は実験的なC4_28を使い、既存恐竜のS3設定とは別です。

## 既存の120 mm版を開く

```powershell
.\skelecad\tools\open_assembly.ps1
.\skelecad\tools\open_full_print_plate.ps1
.\skelecad\tools\open_print_kit.ps1
```

組立と印刷配置は設定から現行版を選びます。印刷キットは現行S3の選定元であるR3比較用です。
印刷ファイルは設定されたスライサーで開きます。これらは配置・嵌合確認用で、
画面からのジョブ別印刷承認と同じ工程ではありません。
`-CheckOnly`を付けるとアプリを起動せず対象ファイルを確認できます。
古い`.lnk`の名称は導入当時のもので、Gitには含まれません。

## ビルドと検証

```powershell
.\skelecad\tools\build.ps1
```

必要な入力画像・外観メッシュを用意すると、CAD、STEP、STL、3MF、
閉じたメッシュ・組立衝突・可動域の検査、CalculiX解析、レビュー画像を生成します。
`build/preview/assembly.png`と`build/review/current/summary.md`がレビュー用出力です。
過去の製作経緯は[変更履歴](docs/CHANGELOG.md)と[設計](docs/DESIGN.md)に残しています。
旧版の入力やテンプレートを必要とする印刷補助処理もあり、全製作工程はcloneだけでは完結しません。

[ローカル接続と保存](docs/LOCAL_WEB_APP.md) · [配布範囲](../THIRD_PARTY_NOTICES.md)
