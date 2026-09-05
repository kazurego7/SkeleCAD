"""Prepare audited editable Bambu projects; slicing belongs to Bambu Studio."""
import json
import shutil
import zipfile
from prepare_workflow_print import package,sha
from slice_workflow_print import cache_context
from workflow_store import write_json


def run(directory,verification_run=False):
    input_context=cache_context([])
    digest=sha(directory/'manifest.json')
    approval_digest=None
    if not verification_run:
        approval=json.loads((directory/'review_approval.json').read_text(encoding='utf-8'))
        if approval.get('accepted') is not True or approval.get('manifest_sha256')!=digest:
            raise ValueError('Current geometry has not been reviewed')
        approval_digest=sha(directory/'review_approval.json')
    output=directory/'print';output.mkdir(exist_ok=True)
    release=output/'release.json'
    try:previous=json.loads(release.read_text(encoding='utf-8'))
    except (OSError,ValueError):previous={}
    write_json(release,{'ready_to_open':False,'ready_to_print':False,'manifest_sha256':digest,'plates':[]})
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if not manifest['parts'] or any(sha(directory/p['filename'])!=p['sha256'] for p in manifest['parts']):
        raise ValueError('Geometry changed')
    reports=None
    if previous.get('artifact_kind')=='bambu_project' and previous.get('manifest_sha256')==digest and previous.get('project_verified') is True:
        try:
            preparation=output/'preparation.json'
            candidate=json.loads(preparation.read_text(encoding='utf-8'))['plates']
            if (sha(preparation)==previous.get('preparation_sha256') and cache_context(candidate)==previous.get('cache_context')
                    and previous['plates'] and all(sha(output/f'plate_{p["plate"]:02d}'/p['filename'])==p['sha256'] for p in previous['plates'])):
                reports=candidate;records=previous['plates']
        except (OSError,ValueError,KeyError):pass
    reused=reports is not None
    if not reused:
        reports=package(directory);records=[]
        if not reports:raise ValueError('No project plates')
        for report in reports:
            folder=output/f'plate_{report["plate"]:02d}'
            source=folder/'input.3mf'
            with zipfile.ZipFile(source) as z:
                if any(n.endswith('.gcode') for n in z.namelist()):raise ValueError('Unexpected sliced content')
            target=folder/f'SkeleCAD_A1mini_plate_{report["plate"]:02d}.3mf'
            shutil.copy2(source,target)
            records.append({'plate':report['plate'],'filename':target.name,'sha256':sha(target),'sliced':False,'geometry_matches_review':True})
    if cache_context([])!=input_context or sha(directory/'manifest.json')!=digest or any(sha(directory/p['filename'])!=p['sha256'] for p in manifest['parts']):
        raise ValueError('Geometry changed during packaging')
    if not verification_run and sha(directory/'review_approval.json')!=approval_digest:raise ValueError('Review changed')
    result={'artifact_kind':'bambu_project','project_verified':True,'ready_to_open':not verification_run,
            'ready_to_print':False,'slicing_verified':False,'verification_run':verification_run,
            'manifest_sha256':digest,'review_approval_sha256':approval_digest,'plates':records,
            'cache_context':cache_context(reports),'preparation_sha256':sha(output/'preparation.json'),'project_reused':reused}
    write_json(release,result);return result
