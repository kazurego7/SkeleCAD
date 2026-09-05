"""Generate the Japanese print handoff only from a completed release audit."""
import json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
params=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
rev=params['project']['revision'];out=ROOT/'build/print_ready'/f'sliced_{rev}'
audit=json.loads((out/'print_audit.json').read_text(encoding='utf-8'))
package=json.loads((ROOT/'build/reports/hybrid_package.json').read_text(encoding='utf-8'))
assert audit['revision']==rev and package['revision']==rev
b=package['assembly_bounds_mm']
lines=[f'# SkeleCAD {rev} 印刷用データ', '',
    f'組立寸法：全長 {b["x"]:.1f} × 幅 {b["y"]:.1f} × 高さ {b["z"]:.1f} mm。9パーツ・8関節。',
    '画像から生成した骨格を12 cmに再設計。ボール6 mm・直径隙間0.6 mmは維持しています。', '',
    '## 対象と設定', '',
    '- Bambu Lab A1 mini、標準0.4 mmノズル、標準Textured PEIプレート。',
    '- Bambu PLA Matte・白。単色印刷。画面の部品色は識別用です。',
    '- 積層0.16 mm（初層0.20 mm）、外周4本、充填15%、自動ツリーサポート。',
    '- ノズル220℃、ベッド55℃。スライサーでの追加拡大・縮小は不要です。', '',
    '本体配置は従来型タイムラプスに非対応です。印刷時はタイムラプスをOFFにしてください。', '',
    '## 印刷の順番', '',
    '1. プレートを清潔にし、白PLA Matteをセットして、まず `fit_kit` の試験片を印刷してください。',
    '2. 冷えてからサポートを除去。1・2・3個の点はそれぞれ直径隙間0.4・0.6・0.8 mmです。本体は2点の0.6 mmです。',
    '3. 無理な力をかけず、取り外しやすさ・ガタ・自重で抜けないことを確認してください。割れる、保持できない場合は本体を印刷する前に調整が必要です。',
    '4. 問題なければ `120mm` の本体を印刷。冷ましてからサポートを慎重に除去し、9パーツを組み立てます。', '',
    '各フォルダーの `.gcode` が印刷経路、`.gcode.3mf` が同じ経路とモデル・設定を含むファイルです。',
    'プリンターへの送信・印刷開始は行っていません。古い1.2.4版のG-codeは使用しないでください。', '',
    '## ファイルと見積もり', '']
for key,title in [('fit_kit','嵌め合い試験片'),('120mm','本体9パーツ')]:
    j=audit['jobs'][key];p=j['slice']['plates'][0];minutes=round(p['seconds']/60)
    lines += [f'### {title}', '',f'- 1プレート、約{minutes//60}時間{minutes%60}分、約{p["grams"]:.2f} g（スライサー見積もり）。',
              f'- 印刷用：[{j["gcode"]}]({key}/{j["gcode"]})',
              f'- 設定込み：[{j["slice"]["file"]}]({key}/{j["slice"]["file"]})',
              f'- [サポート・経路の確認画像]({key}/toolpaths.png)', '']
lines += ['## 検証と残る注意', '',
    '- CAD、STLの閉形状、3MF構造、元形状の保全、静止組立36組の干渉、設定した角度の可動チェックに合格。',
    '- CalculiXの標準骨・ボール軸・基準試験片の計算に合格。恐竜全体の強度や実機の嵌め合いを保証するものではありません。',
    '- 最新パーツとスライス済みモデルの形状・縮尺・機種設定を照合。全パーツが印刷対象で、印刷経路が180 mm範囲内に収まることを確認。',
    '- 温度警告は残っています：OrcaのPLA閾値45℃よりベッド55℃が高いためです。55℃はメーカーのTextured PEI推奨範囲内です。警告を隠す変更はしていません。',
    '- CLIが出力するslice_info内の初層時間には異常値があるため、上記時間は通常の総印刷時間欄を使用しています。',
    '- 細かい歯・爪・浅いソケット縁は繊細です。肉厚・層間強度・保持力・疲労は実物での確認が必要です。小部品の誤飲に注意。子ども向け安全認証品ではありません。', '',
    '温度参考：[Bambu Textured PEI公式](https://us.store.bambulab.com/collections/accessories-for-a1-mini/products/bambu-textured-pei-plate)', '',
    '## 再生成（CUI）', '',
    '`skelecad/tools/build.ps1` → `skelecad/tools/slice_palm_print.ps1` → `skelecad/tools/audit_palm_print.py`。',
    'これらはローカルで生成・スライス・監査する処理です。プリンターを操作する処理は含みません。', '',
    '[監査記録](print_audit.json)', '']
(out/'印刷ガイド.md').write_text('\n'.join(lines),encoding='utf-8')
bundle=out/f'SkeleCAD_{rev}_A1mini_120mm_print.zip'
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
    for file in sorted(out.rglob('*')):
        if file.is_file() and file!=bundle:z.write(file,file.relative_to(out))
print(bundle)
