"""CAD-only shallow-cup fit/capture checks; never predicts physical snap force."""
import json
import math
import FreeCAD as App
import Part
import trex_v2_project as project
from validate_joint_v2 import inserted_stud, axis_sweep

def mesh_front(shape):
    points,_=shape.tessellate(0.005)
    return max(p.x for p in points)

def sampled_mouth(cutter, front, outer_radius):
    # Diagonal meridian avoids the original flex slot. Determine the smallest
    # aperture of the final negative tool, not the pre-trim retention setting.
    best=(float('inf'),0)
    for i in range(401):
        x=front*i/400;low=0.;high=outer_radius+2
        for _ in range(24):
            radius=(low+high)/2
            if cutter.isInside(App.Vector(x,radius/math.sqrt(2),radius/math.sqrt(2)),1e-8,True):low=radius
            else:high=radius
        if high<best[0]:best=(high,x)
    return 2*best[0],best[1]

def main():
    j=project.JOINT;profile=j['socket_profile'];r=j['ball_diameter_mm']/2
    old_outer,old_cut=project.socket_local(legacy_profile=True);old=old_outer.cut(old_cut)
    rows=[]
    for clearance in j['calibration_diametral_clearances_mm']:
        outer,cut=project.socket_local(clearance);shell=outer.cut(cut).removeSplitter()
        ri=r+clearance/2;mid=ri+profile['rim_radius_mm'];rc=profile['retention_diameter_mm']/2+profile['rim_radius_mm']
        effective_mouth,throat_x=sampled_mouth(cut,mesh_front(shell),ri+2*profile['rim_radius_mm'])
        ball=Part.makeSphere(r)
        seated=shell.common(ball).Volume
        symmetry=[]
        for normal in (App.Vector(0,1,0),App.Vector(0,0,1)):
            mirrored=shell.mirror(App.Vector(),normal)
            symmetry.append(shell.cut(mirrored).Volume+mirrored.cut(shell).Volume)
        # At the narrowest section, test offsets spanning the nominal radial
        # play in both transverse directions, not only the centred pull path.
        barrier=[]
        for y in [-clearance/2,0,clearance/2]:
            for z in [-clearance/2,0,clearance/2]:
                moved=Part.makeSphere(r,App.Vector(throat_x,y,z))
                barrier.append({'offset_yz_mm':[y,z],'overlap_mm3':shell.common(moved).Volume})
        withdrawal=[]
        for i in range(25):
            x=i*(throat_x+r+0.5)/24
            overlap=shell.common(Part.makeSphere(r,App.Vector(x,0,0))).Volume
            withdrawal.append({'x_mm':x,'overlap_mm3':overlap})
        directions={}
        for label,axis in [('pitch_positive',(0,1,0)),('pitch_negative',(0,-1,0)),
                           ('yaw_positive',(0,0,1)),('yaw_negative',(0,0,-1)),
                           ('diagonal_positive',(0,1,1)),('diagonal_negative',(0,-1,-1))]:
            maximum,samples=axis_sweep(shell,inserted_stud(),axis)
            directions[label]={'clear_deg':maximum,'samples':samples}
        pitch=min(directions[k]['clear_deg'] for k in ('pitch_positive','pitch_negative'))
        yaw=min(directions[k]['clear_deg'] for k in ('yaw_positive','yaw_negative'))
        rows.append({'diametral_clearance_mm':clearance,'nominal_radial_play_mm':clearance/2,
                     'cavity_diameter_mm':2*ri,'effective_retention_diameter_mm':effective_mouth,
                     'pre_trim_retention_diameter_mm':profile['retention_diameter_mm'],
                     'sampled_throat_x_mm':throat_x,
                     'radial_capture_mm':(j['ball_diameter_mm']-effective_mouth)/2,
                     'spherical_wall_mm':2*profile['rim_radius_mm'],'front_reach_mm':mesh_front(shell),
                     'seated_overlap_mm3':seated,'mirror_difference_mm3':symmetry,'withdrawal':withdrawal,'throat_barrier_samples':barrier,
                     'pitch_clear_deg':pitch,'yaw_clear_deg':yaw,'directional_sweeps':directions,
                     'circumferential_relief':profile.get('circumferential_relief'),
                     'retention_scope':'5.8 mm is the pre-trim profile setting; use sampled withdrawal overlap for the trimmed opening. Snap force is not predicted.',
                     'passed':shell.isValid() and len(shell.Solids)==1 and seated<1e-5
                              and max(symmetry)<1e-5
                              and all(s['overlap_mm3']>1e-4 for s in barrier)
                              and all(d['clear_deg']>=profile['required_motion_deg'] for d in directions.values())})
    nominal=j['socket_diameter_mm']-j['ball_diameter_mm'];main_row=min(rows,key=lambda row:abs(row['diametral_clearance_mm']-nominal))
    report={'joint_version':j['version'],'ball_diameter_mm':j['ball_diameter_mm'],'nominal_diametral_clearance_mm':nominal,
            'old_front_reach_mm':mesh_front(old),'new_front_reach_mm':main_row['front_reach_mm'],'variants':rows,
            'passed':all(r['passed'] for r in rows) and min(main_row['pitch_clear_deg'],main_row['yaw_clear_deg'])>=profile['required_motion_deg'],
            'physical_fit_verified':False,'scope':'CAD seat interference and sampled rigid withdrawal barriers only. No snap-force, wear, fatigue or preload prediction. Nominal radial play remains; print calibration strip and ball before use.'}
    path=project.REPORTS_DIR/'socket_fit_report.json';path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='variants'},indent=2),flush=True)
    for row in rows:print({k:v for k,v in row.items() if k not in ['withdrawal','throat_barrier_samples','directional_sweeps']},flush=True)
    if not report['passed']:raise SystemExit(2)

if __name__=='__main__':main()
