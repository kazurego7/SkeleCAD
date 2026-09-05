"""Real CAD checks for experimental sockets; rigid checks are not holding-force proof."""
import json,math
import FreeCAD as App
import Part
import joint_retention_trial as p

def moved(shape,xyz):return p.shifted(shape,xyz)

def sweep(socket,diameter):
    c=p.CFG;ball=Part.makeSphere(c['ball_diameter_mm']/2)
    stud=ball.fuse(Part.makeCylinder(diameter/2,c['ball_key_handle_x_mm'],App.Vector(),App.Vector(1,0,0)))
    result=[]
    for azimuth in range(0,360,30):
        a=math.radians(azimuth);axis=App.Vector(0,math.cos(a),math.sin(a));clear=0;rows=[]
        # Independently test all samples, record first collision (no skipping holes).
        for angle in range(0,46,2):
            trial=stud.copy();trial.rotate(App.Vector(),axis,angle)
            vol=socket.common(trial).Volume
            rows.append({'angle_deg':angle,'overlap_mm3':vol})
            if vol>0.01:break
            clear=angle
        result.append({'azimuth_deg':azimuth,'clear_deg':clear,'samples':rows})
    return result

def capture(socket):
    r=p.CFG['ball_diameter_mm']/2
    values=[socket.common(Part.makeSphere(r,App.Vector(x/10,0,0))).Volume for x in range(0,51,2)]
    return {'max_centered_withdrawal_overlap_mm3':max(values),'seated_overlap_mm3':values[0]}

def main():
    c=p.CFG;rows=[];key=p.key()
    for number,clearance in enumerate(c['cavity_clearances_mm'],1):
        lower,upper=p.socket_halves(clearance,number)
        # First spherical contact under symmetric closure; no elastic preload
        # is simulated. Production friction must be assessed physically.
        closure=clearance/2
        depth=(closure*c['dovetail_slope']+c['key_side_clearance_mm'])/c['taper_slope']
        assert depth<=c['key_max_insertion_mm'],(number,depth)
        closed=[moved(lower,(0,0,closure)),moved(upper,(0,0,-closure))]
        keys=[moved(key,(-depth,sign*c['rail_center_y_mm'],0)) for sign in (-1,1)]
        overlaps=[a.common(b).Volume for i,a in enumerate(closed+keys) for b in (closed+keys)[i+1:]]
        shell=Part.makeCompound(closed)
        motion=sweep(shell,c['neck_diameter_mm']);cap=capture(shell)
        # Key shoulders must block separation of either half, not just fit.
        lock_overlap=sum(moved(closed[1],(0,0,0.15)).common(k).Volume for k in keys)
        row={'name':f'W{number}','neck_diameter_mm':c['neck_diameter_mm'],'clearance_mm':clearance,
             'half_closure_mm':closure,'key_insertion_at_first_contact_mm':depth,
             'remaining_parting_gap_mm':c['parting_gap_mm']-2*closure,
             'rigid_assembly_max_overlap_mm3':max(overlaps),'key_blocks_opening_overlap_mm3':lock_overlap,
             'motion':motion,'capture':cap}
        row['passed']=max(overlaps)<1e-5 and lock_overlap>0.01 and cap['seated_overlap_mm3']<1e-5 and cap['max_centered_withdrawal_overlap_mm3']>0.01 and min(x['clear_deg'] for x in motion)>=c['required_motion_deg']
        rows.append(row);print(json.dumps({k:v for k,v in row.items() if k!='motion'}),flush=True)
    for var in c['deep_c4']['variants']:
        socket=p.deep_c4(var);motion=sweep(socket,var['neck_diameter_mm']);cap=capture(socket)
        row={'name':var['label'],'neck_diameter_mm':var['neck_diameter_mm'],'motion':motion,'capture':cap}
        row['passed']=cap['seated_overlap_mm3']<1e-5 and cap['max_centered_withdrawal_overlap_mm3']>0.01 and min(x['clear_deg'] for x in motion)>=c['required_motion_deg']
        rows.append(row);print(json.dumps({k:v for k,v in row.items() if k!='motion'}),flush=True)
    report={'passed':all(x['passed'] for x in rows),'variants':rows,
            'physical_retention_verified':False,'scope':'Discrete rigid geometry checks at first contact. No contact stress, plasticity, friction, pull-out force, creep or fatigue proof.'}
    (p.OUT/'mechanical_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if not report['passed']:raise SystemExit(2)

if __name__=='__main__':main()
