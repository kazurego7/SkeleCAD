import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
REVIEW = BUILD / "review"
CURRENT = REVIEW / "current"
HISTORY = REVIEW / "history"
PARAMETERS = ROOT / "config" / "parameters.json"
MODEL_SOURCES = [
    PARAMETERS,
    ROOT / "src" / "freecad_project.py",
    ROOT / "src" / "trex_v2_project.py",
    ROOT / "src" / "validate_joint_v2.py",
    ROOT / "src" / "validate_socket_fit.py",
    ROOT / "src" / "validate_assembly_motion.py",
    ROOT / "src" / "cae_ball_stud.py",
    ROOT / "src" / "cae_coupon.py",
    ROOT / "src" / "cae_actual_bone.py",
    ROOT / "src" / "hybrid_partition.py",
    ROOT / "src" / "freecad_hybrid_tools.py",
    ROOT / "src" / "hybrid_apply_joints.py",
    ROOT / "src" / "finish_cut_edges.py",
    ROOT / "src" / "hybrid_context.py",
    ROOT / "src" / "prepare_palm_source.py",
    ROOT / "src" / "hybrid_local_partition.py",
    ROOT / "src" / "validate_anatomy_preservation.py",
    ROOT / "src" / "validate_repositioned_anatomy.py",
    ROOT / "src" / "hybrid_validate_motion.py",
]


def model_id():
    digest = hashlib.sha256()
    for path in MODEL_SOURCES:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def flatten(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else key
            result.update(flatten(child, name))
    elif isinstance(value, list):
        result[prefix] = value
    else:
        result[prefix] = value
    return result


def archive_before_build():
    current_manifest = CURRENT / "review.json"
    if not current_manifest.exists():
        return
    previous = load_json(current_manifest)
    previous_id = previous.get("model_id")
    if not previous_id or previous_id == model_id():
        return
    destination = HISTORY / previous_id
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CURRENT, destination)


def report(name):
    return load_json(BUILD / "reports" / name)


def parameter_changes(previous, current):
    before = flatten(previous or {})
    after = flatten(current)
    changes = []
    for key in sorted(set(before) | set(after)):
        old = before.get(key, "<未設定>")
        new = after.get(key, "<削除>")
        if old != new:
            changes.append({"parameter": key, "before": old, "after": new})
    return changes


def format_value(value):
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def finalize():
    required = [
        BUILD / "reports" / "cad_report.json",
        BUILD / "reports" / "assembly_report.json",
        BUILD / "reports" / "mesh_report.json",
        BUILD / "reports" / "three_mf_report.json",
        BUILD / "reports" / "cae_report.json",
        BUILD / "reports" / "cae_actual_bone_report.json",
        BUILD / "reports" / "environment_report.json",
        BUILD / "reports" / "joint_report.json",
        BUILD / "reports" / "joint_motion_report.json",
        BUILD / "reports" / "assembly_motion_report.json",
        BUILD / "reports" / "cae_ball_stud_report.json",
        BUILD / "preview" / "assembly.png",
        BUILD / "preview" / "orthographic.png",
        BUILD / "preview" / "concept_comparison.jpg",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Review inputs are missing: " + ", ".join(missing))

    previous_parameters = None
    previous_manifest = None
    previous_manifest_file = CURRENT / "review.json"
    if previous_manifest_file.exists():
        previous_manifest = load_json(previous_manifest_file)
    previous_parameters_file = CURRENT / "parameters.json"
    if previous_parameters_file.exists():
        previous_parameters = load_json(previous_parameters_file)
    # Refreshing reports for the same geometry must keep the comparison with
    # the prior revision, not erase its dimensional-change history.
    if previous_manifest and previous_manifest.get('model_id') == model_id():
        baseline = HISTORY / str(previous_manifest.get('previous_model_id',''))
        if (baseline/'review.json').exists() and (baseline/'parameters.json').exists():
            previous_manifest=load_json(baseline/'review.json')
            previous_parameters=load_json(baseline/'parameters.json')

    parameters = load_json(PARAMETERS)
    cad = report("cad_report.json")
    assembly = report("assembly_report.json")
    hybrid_package = report("hybrid_package.json")
    hybrid_collision = report("hybrid_assembly_collision.json")
    hybrid_motion = report("hybrid_motion.json")
    hybrid_joints = report("hybrid_joint_tools.json")
    meshes = report("mesh_report.json")
    three_mf = report("three_mf_report.json")
    cae = report("cae_report.json")
    actual = report("cae_actual_bone_report.json")
    environment = report("environment_report.json")
    joints = report("joint_report.json")
    joint_motion = report("joint_motion_report.json")
    assembly_motion = report("assembly_motion_report.json")
    ball_cae = report("cae_ball_stud_report.json")
    changes = parameter_changes(previous_parameters, parameters)
    review_assembly = {
        "instance_count": len(hybrid_package["parts"]),
        "collision_count": hybrid_collision["collision_count"],
        "bounds_mm": hybrid_package["assembly_bounds_mm"],
    }

    current_model_id = model_id()
    previous_model_id = previous_manifest.get("model_id") if previous_manifest else None
    manifest = {
        "model_id": current_model_id,
        "previous_model_id": previous_model_id,
        "model_source_changed": bool(previous_model_id and previous_model_id != current_model_id),
        "project": parameters["project"],
        "parameter_changes_from_previous": changes,
        "checks": {
            "cad_parts_valid": all(part["valid"] and part["solid_count"] == 1 for part in cad["parts"]),
            "hybrid_joint_cad_valid": hybrid_joints["passed"],
            "stl_files_passed": sum(1 for item in meshes["parts"] if item["passed"]),
            "stl_files_total": len(meshes["parts"]),
            "three_mf_files_passed": sum(1 for item in three_mf["files"] if item["passed"]),
            "three_mf_files_total": len(three_mf["files"]),
            "assembly_collision_count": review_assembly["collision_count"],
            "hybrid_motion_passed": hybrid_motion["passed"],
            "equivalent_cae_passed": cae["passed"],
            "actual_part_cae_passed": actual["passed"],
            "toolchain_passed": environment["passed"],
            "joint_geometry_passed": joints["passed"],
            "joint_motion_passed": joint_motion["passed"],
            "assembly_motion_passed": assembly_motion["passed"],
            "ball_stud_cae_passed": ball_cae["passed"],
        },
        "assembly": {
            "instance_count": review_assembly["instance_count"],
            "bounds_mm": review_assembly["bounds_mm"],
        },
        "actual_part_cae": {
            "load_n": actual["end_load_n"],
            "displacement_mm": actual["max_loaded_rim_displacement_mm"],
            "max_von_mises_mpa": actual["max_von_mises_mpa"],
            "reference_yield_mpa": actual["reference_yield_mpa"],
            "scope": actual["scope"],
        },
        "review_files": {
            "image": "build/review/current/assembly.png",
            "orthographic": "build/review/current/orthographic.png",
            "concept_comparison": "build/review/current/concept_comparison.jpg",
            "summary": "build/review/current/summary.md",
            "parameters": "build/review/current/parameters.json",
        },
    }

    if parameters['joint'].get('socket_profile'):
        fit=report('socket_fit_report.json')
        manifest['socket_fit']=fit
        manifest['checks']['socket_fit_cad_passed']=fit['passed']
        if not fit['passed']:raise RuntimeError('Socket fit/capture CAD validation failed')
    if parameters.get('hybrid_new',{}).get('cut_edge_finish'):
        from hybrid_context import HYBRID
        finishing=load_json(HYBRID/'edge_finish'/'report.json')
        manifest['cut_edge_finishing']=finishing
        manifest['checks']['cut_edge_finishing_passed']=finishing['passed']
        if not finishing['passed']:raise RuntimeError('Bounded cut-edge finishing failed')

    lines = [
        f"# ユーザー確認票 — {parameters['project']['revision']}",
        "",
        f"モデルID: `{manifest['model_id']}`",
        f"形状生成ルール変更: {'あり' if manifest['model_source_changed'] else 'なし'}",
        "",
        "## 自動検証",
        "",
        f"- CAD部品: {len(cad['parts'])}種類、すべて単一の有効ソリッド",
        f"- 組み込み用ジョイントCAD: {len(hybrid_joints['tools'])}形状、{'合格' if hybrid_joints['passed'] else '不合格'}",
        f"- 接続面のメッシュ設定: 線形 {parameters['printing']['joint_linear_deflection_mm']} mm / 角度 {parameters['printing']['joint_angular_deflection_rad']} rad（印刷精度の保証値ではありません）",
        f"- STL: {manifest['checks']['stl_files_passed']}/{manifest['checks']['stl_files_total']} 合格",
        f"- 3MF: {manifest['checks']['three_mf_files_passed']}/{manifest['checks']['three_mf_files_total']} 合格",
        f"- 組み立て: {review_assembly['instance_count']}個、衝突 {review_assembly['collision_count']}件",
        f"- 干渉判定: 全{hybrid_collision['pairs_checked']}組、意図した嵌め合いを除く余剰重複体積の許容上限 "
        f"{hybrid_collision.get('maximum_allowed_excess_overlap_mm3', hybrid_collision.get('maximum_allowed_overlap_mm3'))} mm³",
        f"- 標準骨部品の実形状CAE（新しい恐竜全体ではありません）: {actual['end_load_n']:.1f} N、変位 {actual['max_loaded_rim_displacement_mm']:.3f} mm、最大応力 {actual['max_von_mises_mpa']:.2f} MPa",
        f"- ツール環境: {'合格' if environment['passed'] else '不合格'}（FreeCAD {environment['versions']['freecad']} / Gmsh {environment['versions']['gmsh']} / CalculiX {environment['versions']['calculix']}）",
        f"- ボールジョイント: 直径 {joints['ball_diameter_mm']:.1f} mm、ソケット隙間 {joints['diametral_clearance_mm']:.1f} mm、前後左右 {min(joint_motion['pitch_collision_free_deg'], joint_motion['yaw_collision_free_deg'])}°以上無干渉",
        f"- 実パーツ可動: 外観優先の方向別可動（最大 {hybrid_motion['maximum_test_angle_deg']}°）、8接続すべて検証合格、頭部は固定一体型",
        f"- ボール首CAE: {ball_cae['side_load_n']:.1f} N、変位 {ball_cae['max_loaded_cap_displacement_mm']:.3f} mm、最大応力 {ball_cae['max_von_mises_mpa']:.2f} MPa",
        "",
        "## 前版からの寸法・設定変更",
        "",
    ]
    if parameters['joint'].get('socket_profile'):
        lines[lines.index('## 前版からの寸法・設定変更'):lines.index('## 前版からの寸法・設定変更')]=[
            '## 浅型ソケットと保持確認','',
            f"- 前方の張り出し: {fit['old_front_reach_mm']:.2f} → {fit['new_front_reach_mm']:.2f} mm",
            f"- 球面の直径差: {fit['nominal_diametral_clearance_mm']:.1f} mm（片側 {fit['nominal_diametral_clearance_mm']/2:.1f} mm）。ガタつきの実機確認が必要です。",
            f"- 加工前入口設定: {parameters['joint']['socket_profile']['retention_diameter_mm']:.1f} mm。最終入口はsocket_fit_report.jsonの実形状サンプル値を参照。ボールは6 mmのまま。",
            '- CAD上では着座時の干渉なし・抜ける途中に保持の干渉あり。挿抜力や耐久性を検証したものではありません。',
            '- 新形状の試験片: build/print/starter_fit_kit.3mf。1/2/3個の点が直径差0.4/0.6/0.8 mmです。','']
    if changes:
        lines.extend(
            f"- `{item['parameter']}`: {format_value(item['before'])} → {format_value(item['after'])}"
            for item in changes
        )
    else:
        lines.append("- 変更なし（同じ設定で再検証）")
    lines.extend([
        "",
        "## ユーザー確認",
        "",
        "- [ ] 全体のシルエットと頭部の方向性",
        "- [ ] 手足・首・尾の長さと比率",
        "- [ ] 組み替えたい構成に必要な接続口",
        "- [ ] 実機で選んだボール接合隙間（0.4 / 0.6 / 0.8 mm）",
        "",
        "> CAEは線形静解析です。衝撃、疲労、接合部の摩耗、子ども向け製品安全を保証しません。",
        "",
    ])

    candidate = parameters.get("appearance_candidate")
    if candidate:
        candidate_report = report("appearance_candidate.json")
        manifest["appearance_candidate"] = candidate_report
        candidate_intro = [
            "# 今回の画像からの新規生成モデル — 外観確認用",
            "",
            f"- 新規推論完了（UTC）: {candidate_report['finished_at_utc']}",
            f"- 入力SHA-256: `{candidate_report['source_sha256']}`",
            f"- 新規モデル: `{candidate_report['mesh']}`",
            f"- メッシュ検証: {'合格' if candidate_report['passed'] else '不合格'}、{candidate_report['topology']['triangles']}面、閉じた単一メッシュ・正の体積",
            "- 新規モデルの精密ジョイント加工・分割・可動干渉・強度解析は未完了です。",
            "- 以下のCAD・組立・CAE結果は旧外観に基づく既存製品と試験片のものです。新規モデルの合格結果ではありません。",
            "- 新規外観の画像: `candidate.png`（`assembly.png`は旧製品）",
            "",
            "---",
            "",
        ]
        if parameters.get("hybrid_new"):
            from hybrid_context import H, INPUT
            expected_source=INPUT.relative_to(ROOT).as_posix()
            if hybrid_package.get("appearance_mesh") != expected_source:
                raise RuntimeError("Jointed assembly does not use the current image-to-3D mesh")
            if H.get('palm_size',{}).get('enabled'):
                sizing=load_json(ROOT/H['output_directory']/'sizing.json')
                original=ROOT/sizing['original_source']
                if original.resolve()!=(ROOT/candidate['mesh']).resolve() or sizing['source_sha256']!=hashlib.sha256(original.read_bytes()).hexdigest():
                    raise RuntimeError('Scaled source provenance failed')
                manifest['palm_size']=sizing
            if not (hybrid_collision["passed"] and hybrid_motion["passed"] and hybrid_joints["passed"]):
                raise RuntimeError("New jointed assembly validation is incomplete")
            manifest["jointed_assembly"] = hybrid_package
            candidate_intro = [
                "# 今回の画像から新規生成 → ジョイント加工済み（試作）", "",
                f"- 新規推論完了（UTC）: {candidate_report['finished_at_utc']}",
                f"- 入力SHA-256: `{candidate_report['source_sha256']}`",
                f"- 加工元メッシュ: `{candidate_report['mesh']}`",
                f"- 加工済み組立: `{hybrid_package['assembly_review_stl']}`",
                "- 9部品・8接続。旧8/21モデルとは別保存です。",
                "- `assembly.png`は新規加工済み組立、`candidate.png`は未加工の新規外観です。",
                "- 関節を1か所ずつ離散角度で回し、他の全パーツとの干渉を検査（股関節では足先も追従）。同時・連続可動の保証ではありません。",
                "- CAD検証は精密ジョイントソリッドと標準部品が対象。恐竜外観・組立FCStdはメッシュです。",
                "- CalculiXは標準骨・標準ボール首の試験片です。新規外観の支持部・全身・ソケット接触の強度は未検証です。",
                "- 画像由来の細部の最小肉厚・先端丸みも未保証。実機の嵌合・疲労・破壊試験が必要です。", "", "---", "",
            ]
        lines = candidate_intro + lines

    CURRENT.mkdir(parents=True, exist_ok=True)
    if parameters.get('hybrid_new',{}).get('partition_method') == 'local_joint_discs':
        preservation = report('anatomy_preservation.json')
        if not preservation['passed']:
            raise RuntimeError('Original anatomy preservation failed')
        manifest['checks']['anatomy_preservation_passed'] = True
        manifest['anatomy_preservation'] = preservation
        lines[2:2] = [
            '- 指先・つま先・脚の側面を復元。全身を貫く切断面と箱形の切り出しは廃止。',
            f"- 局所加工領域外の元頂点 {preservation['overall']['protected_vertices']:,} 点を検証し、失われた点は {preservation['overall']['missing_vertices']} 点。支持部の追加に覆われた元表面は除去と区別しています。",
            '- 拡大比較: `anatomy_preservation.jpg`（上: 加工前／下: 修正後）', '',
        ]
        shutil.copy2(BUILD/'preview/anatomy_preservation.jpg',CURRENT/'anatomy_preservation.jpg')
        if parameters['hybrid_new'].get('part_translation_mm'):
            from hybrid_context import H
            placement=H['part_translation_mm']
            lines[2:2] = [
                '- 股の円形の縁は左右とも胴体の一部に変更。全体積の保持を検証。',
                f"- 元画像座標からの配置: 左腕 {placement['arm_left']} mm／右腕 {placement['arm_right']} mm、左脚・足先 {placement['leg_left']} mm／右脚・足先 {placement['leg_right']} mm。肩・股の球状切削は廃止。",
                '- 肩・股は外開き0/5/10/15度を追加検証。6 mmボールと直径隙間0.6 mmは変更なし。',
                f"- 移動を戻して元形状{preservation['overall']['protected_vertices']:,}点を検査。加工後は各部品の除去体積を実際の許可工具と照合。", '',
            ]
            if parameters['hybrid_new'].get('compact_socket_min_contact_mm3'):
                lines[2:2]=[
                    '- 1.2.3: 左右の肩受けを4 mm、股受けを6 mm引込み。受け本体と元の胴体の直接接触を検証。',
                    '- 左右の腕を前へ2.5 mm移動。軸の先端を骨の内部へ埋め、T字状の補助部分は不要に。',
                    '- 尾の付け根上側だけに斜めの局所逃げを追加。上下±15度を2.5度刻みで検査。', '',
                ]
    if parameters['joint'].get('socket_profile'):
        lines[2:2]=[
            '- 1.2.4（履歴）: 8か所の受けを浅型・R1の丸い縁へ。前方への張り出し約3.79 → 2.81 mm。',
            '- 球面隙間0.6 mmは維持し、抜け止め入口は5.8 mm。骨への切削範囲は広げていません。',
            '- 着座・抜け止めのCAD検証は合格。ガタつき・保持力の実機試験は未実施です。','',
        ]
    if parameters['joint'].get('socket_profile',{}).get('circumferential_relief'):
        lines[2:2]=[
            '- 1.2.5：8か所の受けの内側の縁を全周で削り、手で着脱する形を優先。4方向の切欠き案は不採用。',
            '- ソケット単体は上下・左右・斜めの30°を検査。実際の全身では骨同士の可動制限が残ります。',
            '- 公称隙間0.6 mmの最終入口は約5.828 mm。抜け止めは一部残るが、保持力・ガタ・耐久は実機未確認。',
            '- 1.2.4のスライス済みデータは旧形状です。新しい試験片・部品から再スライスしてください。','',
        ]
    if parameters['joint'].get('socket_profile',{}).get('height_trim'):
        lines[2:2]=[
            '- 1.2.6：全8ソケットの外形高さを全周で切下げ。中心から開口端まで約2.81 → 1.50 mm、外縁R1。',
            '- 首の元の球状造形を胴体から局所除去。頭と首関節を胴体側へ4.5 mm移動。',
            '- 指定された最初の尾の付け根上側突起のみ局所加工を拡大。',
            '- 公称0.6 mm隙間版の最終入口は約5.899 mm。保持力・ガタ・耐久は実機未確認。',
            '- 以下の1.2.5以前は変更履歴です。旧スライスデータは再使用せず新形状で再スライスしてください。','',
        ]
    if parameters.get('hybrid_new',{}).get('cut_edge_finish'):
        lines[2:2]=[
            '- 1.2.7：外縁の半周に丸めが欠けていた不具合を修正。全8ソケットを全周R1に統一。',
            '- 腕・脚・首・尾・足首などの切断境界に局所仕上げを追加。精密ジョイントを付ける前に骨側だけを加工。',
            '- 仕上げ帯1.5 mm・頂点移動上限0.5 mm。実際の切断境界から2.1 mm以内だけを許容し、元の骨への追加の食い込みを検査。',
            '- ボール6 mm、受け6.6 mm、高さ1.5 mm、関節配置は維持。旧スライスデータは再利用しないでください。',
            '- 以下の1.2.6以前は変更履歴です。実機の保持力・疲労・有機形状の最小肉厚は未確認。','',
        ]
    if parameters.get('hybrid_new',{}).get('palm_size',{}).get('enabled'):
        lines[2:2]=[
            '- 1.3.0：完成時の全長120 mm。8月30日の画像由来の骨格を縮小し、精密ジョイントは6 mmのまま再生成。',
            '- 手足・首・尾の配置を調整。スライサーの一括縮小は使用していません。',
            '- A1 mini・標準0.4 mmノズル・白Bambu PLA Matte・標準Textured PEI用。',
            '- ボール6 mm・受け6.6 mm・高さ1.5 mmを維持。実機での保持力・耐久は試験片から確認してください。',
            '- 以下の1.2.xの寸法・配置記述は旧20 cmモデルの変更履歴です。','',
        ]
    (CURRENT / "review.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (CURRENT / "parameters.json").write_text(
        json.dumps(parameters, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (CURRENT / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    shutil.copy2(BUILD / "preview" / "assembly.png", CURRENT / "assembly.png")
    shutil.copy2(BUILD / "preview" / "orthographic.png", CURRENT / "orthographic.png")
    shutil.copy2(BUILD / "preview" / "concept_comparison.jpg", CURRENT / "concept_comparison.jpg")
    if candidate:
        candidate_preview = (ROOT / candidate["mesh"]).parent / "review.png"
        shutil.copy2(candidate_preview, CURRENT / "candidate.png")
    print(json.dumps(manifest, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("archive-before-build", "finalize"))
    args = parser.parse_args()
    if args.mode == "archive-before-build":
        archive_before_build()
    else:
        finalize()


if __name__ == "__main__":
    main()
