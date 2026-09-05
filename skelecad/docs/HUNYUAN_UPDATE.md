# Hunyuan推論環境の更新検証（2026-09-05）

最新依存で実際の画像→3D生成が成功したため、新しい推論環境を採用しました。
その後の速度・形状比較と採用設定は[最適化記録](HUNYUAN_OPTIMIZATION.md)を参照してください。
Hunyuan3D 2.1本体は公式HEADと一致しており、ソースの改造やモデル重みの変更はありません。
公式ソースcommit: `82920d643c0dc2f7bfd7255f45f62d386edfe60c`。

## 更新内容

| 対象 | 従来 | 採用版 |
| --- | --- | --- |
| Python | 3.10.16 | 3.14.7 |
| PyTorch | 2.5.1+cu124 | 2.14.0+cu132 |
| torchvision | 0.20.1+cu124 | 0.29.0+cu132 |
| Transformers | 4.46.0 | 5.16.1 |
| Diffusers | 0.30.0 | 0.40.0 |
| Accelerate | 1.1.1 | 1.14.0 |
| Hugging Face Hub | 0.30.2 | 1.30.0 |
| NumPy | 1.24.4 | 2.5.2 |

全66パッケージは`requirements-inference.lock`に固定しています。
`config/toolchain.json`の`inference_python`が採用環境を指定します。
CUDA 13.2版はRTX 3060・ドライバー616.64で確認しました。ドライバーは変更していません。

## 比較方法と結果

自作の`assets/workflow_tests/blue_robot.png`を共通の透過入力にし、
同じモデル重み・seed 3407・50ステップ・guidance 5.0・解像度384で、
従来環境と更新候補の両方から実際にGLBを生成しました。
どちらも通常の後処理で全長120 mmにそろえています。

| 検証 | 結果 |
| --- | --- |
| 依存関係の整合性 | 合格 |
| Hunyuan読み込み・CUDA動作 | 両環境で合格 |
| 50ステップの形状生成と書き出し | 両環境で成功 |
| 後処理後の閉じたメッシュ・面の向き | 両環境で正常、各1成分 |
| 三角形数 | 従来461,290 → 更新461,140 |
| 体積差 | -0.04465% |
| 双方向の最近傍頂点距離 | 平均0.02138 mm、95%点0.06062 mm、最大0.21439 mm |
| プレビュー確認 | 主な形状や部位に大きな崩れなし |

最近傍頂点距離は近似的な形状比較であり、厳密な面間距離ではありません。
1つの検証画像による結果で、すべての入力の生成品質を保証するものではありません。
これはSkeleCADで使う形状生成経路の検証です。Hunyuanのテクスチャ生成経路は対象外です。
推論速度は今回の条件では従来とほぼ同程度でした。

候補と本番用環境の全パッケージ版が一致することを確認し、本番設定経由でも
Hunyuanの読み込みとGPU計算を確認しました。ツールチェーン整合性検査も実行しました。
比較用生成物は検証後にユーザーが削除しました。既存ユーザーモデルや製作寸法・材料は
変更していません。そのため既存組立のCAD/CAEビルドは今回再実行していません。

## 環境の再現

```powershell
uv venv .tools/hunyuan3d-2.1-modern-venv --python 3.14.7
uv pip sync --python .tools/hunyuan3d-2.1-modern-venv/Scripts/python.exe --torch-backend cu132 skelecad/requirements-inference.lock
```

動作確認後、ユーザーの希望により設定から旧環境への切り戻し項目を削除しました。
使用する推論環境は`.tools/hunyuan3d-2.1-modern-venv/`です。
旧環境`.tools/hunyuan3d-2.1-venv/`と検証環境`.tools/hunyuan-inference-candidate/`の
物理削除はユーザーが実施し、両フォルダが存在しないことを確認済みです。
モデル重みや既存ユーザー生成物は維持しています。
新しい設定は次に開始する推論に反映されます。既存の生成物は作り直しません。

[Hunyuan公式ソース](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1) ·
[PyTorch公式](https://pytorch.org/get-started/locally/) ·
[Transformers配布](https://pypi.org/project/transformers/) ·
[Diffusers配布](https://pypi.org/project/diffusers/)
