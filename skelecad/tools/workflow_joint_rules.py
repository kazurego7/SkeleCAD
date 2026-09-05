"""Pure validation rules shared by workflow generation, API and viewer data."""
from __future__ import annotations
import math


def minimum_joint_spacing(parameters):
    workflow=parameters['image_workflow']['manufacturing']
    trial=parameters['joint_retention_trial'];deep=trial['deep_c4']
    variant=next(v for v in deep['variants'] if v['label']==workflow['joint_variant'])
    clearance=variant.get('cavity_clearance_mm',deep['cavity_clearance_mm'])
    return float(trial['ball_diameter_mm']+clearance+2*deep['wall_mm'])


def nearby_socket_spacing(parameters):
    """Distance where two joints on one part should share that socket owner.

    The socket shell diameter alone is enough for the hard placement rejection.
    Its mounting bridge can extend laterally, though, so nearby joints which
    share an anatomy part should put both sockets on that common part.  This is
    derived from the selected socket and bridge geometry, not a second nominal
    joint dimension.
    """
    return minimum_joint_spacing(parameters)+2*float(parameters['image_workflow']['manufacturing']['socket_bridge_radius_mm'])


def spacing_conflicts(candidates,names,minimum):
    selected=[c for c in candidates if c.get('name') in names and isinstance(c.get('center'),list) and len(c['center'])==3]
    conflicts=[]
    for index,a in enumerate(selected):
        for b in selected[index+1:]:
            distance=math.dist(a['center'],b['center'])
            if distance<minimum-1e-6:
                conflicts.append({'a':a['name'],'b':b['name'],'distance_mm':distance,'minimum_mm':minimum})
    return conflicts
