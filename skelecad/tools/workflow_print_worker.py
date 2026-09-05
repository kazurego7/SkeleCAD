"""Review-bound print preparation worker, no printer/network dispatch."""
import argparse
import json
import os
import traceback
from pathlib import Path
from workflow_store import now,process_identity,write_json


def run(directory):
    path=directory/'state.json';state=json.loads(path.read_text(encoding='utf-8'))
    def update(**fields):state.update(updated_at=now(),**fields);write_json(path,state)
    update(stage='printing',message='確認した姿勢を検証し、配置・サポート設定付きの3MFを準備しています',
           pid=os.getpid(),process_identity=process_identity(os.getpid()))
    try:
        from audit_workflow_motion import verify_review_pose
        from prepare_workflow_project import run as prepare_print
        folder=directory/'machining'/state['mechanical_revision']
        approval=json.loads((folder/'review_approval.json').read_text(encoding='utf-8'))
        verify_review_pose(folder,approval['pose'])
        report=prepare_print(folder)
        downloads=[]
        for plate in report['plates']:
            downloads.append({'plate':plate['plate'],'filename':plate['filename'],'sha256':plate['sha256'],
                              'sliced':False,
                              'url':f'../api/jobs/{state["id"]}/files/p_{folder.name}_{plate["plate"]:02d}.3mf'})
        update(stage='print_ready',prints=downloads,message=f'Bambu用3MFの準備完了（{len(downloads)}プレート・サポート設定済み）。スライスはBambu Studioで行ってください。')
    except Exception as exc:
        traceback.print_exc();update(stage='print_failed',message='印刷準備の検証を完了できませんでした。加工済みモデルは保持しています。',error=str(exc))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job-directory',type=Path,required=True)
    run(parser.parse_args().job_directory.resolve())
