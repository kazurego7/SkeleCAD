"""Headless native Bambu slicing with artifact audits; never sends to a printer."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from prepare_workflow_print import package,audit_input,BAMBU,PARAMS,write,sha
from audit_orca_print import sliced_audit
from workflow_store import write_json


def cache_context(reports):
    project=Path(__file__).resolve().parents[1]
    value={'plates':reports,'parameters':sha(project/'config/parameters.json'),
           'toolchain':sha(project/'config/toolchain.json'),
           'template':sha(project/'build/print_ready/bambu_1.3.0/input/fit_kit.3mf'),
           'code':{str(path.relative_to(project)):sha(path) for folder in ('src','tools')
                   for path in sorted((project/folder).glob('*.py'))}}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def reuse_verified(directory, previous, digest, approval_digest, verification_run):
    """Reuse only identical, previously audited bytes and the same audit implementation.

    The caller has independently checked the current review pose. Rebuilding XML
    and re-parsing G-code adds no evidence when every input, setting, tool and
    output byte is unchanged. A missing/old proof falls through to full auditing.
    """
    if (previous.get('verification_run') is not True or previous.get('slicing_verified') is not True
            or previous.get('ready_to_print') is not False or previous.get('manifest_sha256')!=digest):return None
    try:
        preparation=directory/'print/preparation.json'
        if sha(preparation)!=previous.get('preparation_sha256'):return None
        reports=json.loads(preparation.read_text(encoding='utf-8'))['plates']
        context=cache_context(reports)
        if context!=previous.get('cache_context'):return None
        for key in ('executable','library'):
            if sha(Path(BAMBU[key]))!=BAMBU[key+'_sha256']:return None
        manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        if not manifest['parts'] or not reports:return None
        for part in manifest['parts']:
            target=directory/part['filename']
            if target.resolve().parent!=directory.resolve() or sha(target)!=part['sha256']:return None
        records=previous.get('plates',[])
        if len(records)!=len(reports) or len({p['plate'] for p in records})!=len(records):return None
        if {p['plate'] for p in records}!={p['plate'] for p in reports}:return None
        for record in records:
            filename=f'SkeleCAD_A1mini_plate_{record["plate"]:02d}.3mf'
            if record['filename']!=filename:return None
            target=directory/'print'/f'plate_{record["plate"]:02d}'/filename
            if target.resolve()!=target or sha(target)!=record['sha256']:return None
        if (sha(directory/'manifest.json')!=digest or cache_context(reports)!=context
                or (not verification_run and sha(directory/'review_approval.json')!=approval_digest)):return None
        return {**previous,'review_approval_sha256':approval_digest,'verification_run':verification_run,
                'ready_to_print':not verification_run,'physical_fit_verified':False,'printer_started':False,
                'plates':[{**p,'speculative_slice_reused':True} for p in records]}
    except (OSError,ValueError,KeyError,TypeError):return None


def run(directory,verification_run=False):
    digest=sha(directory/'manifest.json')
    approval_digest=None
    if not verification_run:
        approval=json.loads((directory/'review_approval.json').read_text(encoding='utf-8'))
        if approval.get('manifest_sha256')!=digest or approval.get('accepted') is not True:
            raise ValueError('Current geometry has not been reviewed')
        approval_digest=sha(directory/'review_approval.json')
    attempt=uuid.uuid4().hex
    output=directory/'print';output.mkdir(exist_ok=True)
    release=output/'release.json'
    previous={}
    if release.exists():
        try:previous=json.loads(release.read_text(encoding='utf-8'))
        except ValueError:pass
        shutil.copy2(release,output/f'release_before_{attempt}.json')
    write_json(release,{'manifest_sha256':digest,'attempt':attempt,
                        'ready_to_print':False,'slicing_verified':False,'plates':[]})
    reused=reuse_verified(directory,previous,digest,approval_digest,verification_run)
    if reused is not None:
        write_json(release,reused)
        return reused
    reports=package(directory);result=[]
    if not reports:raise ValueError('No print plates were prepared')
    context=cache_context(reports)
    reuse=(previous.get('verification_run') is True and previous.get('slicing_verified') is True
           and previous.get('manifest_sha256')==digest and previous.get('cache_context')==context)
    for report in reports:
        folder=directory/'print'/f'plate_{report["plate"]:02d}'
        # Never let a successful exit without output reuse a prior result.json/3MF.
        attempt_folder=folder/'attempts'/attempt
        attempt_folder.mkdir(parents=True,exist_ok=False)
        shutil.copy2(folder/'input.3mf',attempt_folder/'input.3mf')
        target=attempt_folder/f'SkeleCAD_A1mini_plate_{report["plate"]:02d}.3mf'
        # Each attempt has separate outputs; no process/slicer global settings.
        startup=None
        if os.name=='nt':
            startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
        command=[BAMBU['executable'],'--slice','1','--arrange','0','--orient','0',
                 '--outputdir',str(attempt_folder),'--export-3mf',target.name,str(attempt_folder/'input.3mf')]
        cached=[p for p in previous.get('plates',[]) if p.get('plate')==report['plate']] if reuse else []
        stable=folder/target.name
        reused=bool(len(cached)==1 and cached[0].get('filename')==target.name and stable.is_file()
                    and sha(stable)==cached[0].get('sha256') and (folder/'result.json').is_file())
        if reused:
            shutil.copy2(stable,target);shutil.copy2(folder/'result.json',attempt_folder/'result.json')
            (attempt_folder/'slice.log').write_text('Reused speculative slicing; all output audits rerun.\n',encoding='utf-8')
        else:
            # Bambu's Windows process launch does not accept a deeply nested cwd.
            # Keep its private workspace short; retain the completed evidence in
            # the revision's attempt directory after the process exits.
            with tempfile.TemporaryDirectory(prefix='sk_slice_') as temporary:
                work=Path(temporary)
                shutil.copy2(attempt_folder/'input.3mf',work/'input.3mf')
                command=[BAMBU['executable'],'--slice','1','--arrange','0','--orient','0',
                         '--outputdir',str(work),'--export-3mf',target.name,str(work/'input.3mf')]
                with (attempt_folder/'slice.log').open('wb') as log:
                    process=subprocess.run(command,cwd=work,stdout=log,stderr=subprocess.STDOUT,startupinfo=startup,
                                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for name in ('result.json',target.name):
                    if (work/name).is_file():shutil.copy2(work/name,attempt_folder/name)
            if process.returncode:raise ValueError(f'Bambu slicing failed on plate {report["plate"]}')
        code=json.loads((attempt_folder/'result.json').read_text(encoding='utf-8'))
        if code['return_code']!=0:raise ValueError('Bambu did not report success')
        audit_input(target,directory,report)
        sliced=sliced_audit(target)
        if len(sliced['plates'])!=1:raise ValueError('Unexpected plate count')
        plate=sliced['plates'][0]
        if sorted(plate['objects'])!=sorted(p['name'] for p in report['parts']):raise ValueError('Slicer omitted or duplicated parts')
        if not plate['preview_bbox_within_bed']:raise ValueError('Supports or brim are outside the print bed')
        with zipfile.ZipFile(target) as z:
            settings=json.loads(z.read('Metadata/project_settings.config'))
            support=PARAMS['printing']['support_defaults']
            for key,value in {'enable_support':'1','support_type':support['type'],
                              'support_top_z_distance':str(support['top_z_distance_mm']),
                              'support_object_xy_distance':str(support['object_xy_distance_mm']),
                              'support_interface_spacing':str(support['interface_spacing_mm']),
                              'support_interface_speed':[str(support['interface_speed_mm_s'])],
                              'support_interface_top_layers':str(support['interface_top_layers']),
                              'nozzle_diameter':['0.4'],
                              'printer_model':'Bambu Lab A1 mini','curr_bed_type':'Textured PEI Plate',
                              'filament_settings_id':[BAMBU['filament_preset']],'textured_plate_temp':['55']}.items():
                if settings[key]!=value:raise ValueError(f'Unexpected print setting {key}')
            header=ET.fromstring(z.read('Metadata/slice_info.config')).find('header')
            values={item.get('key'):item.get('value') for item in header}
            if values.get('X-BBL-Client-Version')!=BAMBU['version']:raise ValueError('Wrong slicer output version')
            gcode=z.read('Metadata/plate_1.gcode').decode()
            if not re.search(r'^M190 S55\b',gcode,re.M):raise ValueError('Bed temperature mismatch')
            support_generated='; FEATURE: Support' in gcode
            (attempt_folder/'plate.png').write_bytes(z.read('Metadata/plate_1.png'))
        unexpected=[w for w in plate['warnings'] if w.get('msg')!='not_support_traditional_timelapse']
        if unexpected:raise ValueError(f'Slicer warnings require review: {unexpected}')
        record={'plate':report['plate'],'filename':target.name,'sha256':sha(target),'slice':sliced,'attempt':attempt,
                'support_enabled':True,'support_generated':support_generated,'geometry_matches_review':True,
                'speculative_slice_reused':reused}
        write(attempt_folder/'audit.json',record)
        # Stable download names are published only after this attempt's audits.
        for name in (target.name,'plate.png','result.json','audit.json','slice.log'):
            shutil.copy2(attempt_folder/name,folder/name)
        result.append(record)
    if sha(directory/'manifest.json')!=digest:raise ValueError('Geometry changed during slicing')
    if cache_context(reports)!=context:raise ValueError('Print settings or code changed during slicing')
    if not verification_run and sha(directory/'review_approval.json')!=approval_digest:
        raise ValueError('Review changed during slicing')
    # Recheck every part after all plates, not just the plate currently slicing.
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if any(sha(directory/p['filename'])!=p['sha256'] for p in manifest['parts']):
        raise ValueError('Geometry changed during slicing')
    report={'manifest_sha256':digest,'review_approval_sha256':approval_digest,'attempt':attempt,
            'cache_context':context,
            'preparation_sha256':sha(output/'preparation.json'),
            'plates':result,'slicing_verified':True,'verification_run':verification_run,
            'ready_to_print':not verification_run,'physical_fit_verified':False,'printer_started':False}
    write_json(release,report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--revision-directory',type=Path,required=True)
    parser.add_argument('--verification-run',action='store_true');args=parser.parse_args()
    print(json.dumps(run(args.revision_directory.resolve(),args.verification_run),indent=2))
