"""R3 incremental holding-fit plate, based on the physically preferred H3."""
import prepare_retention_print as shared

def main():
    c=shared.PARAMS['joint_holding_step_trial'];shared.C={**shared.C,**c}
    shared.BASE=shared.ROOT/c['output_directory']
    names=[v['label']+suffix for v in c['variants'] for suffix in ('_socket','_ball_key')]
    shared.main(names,'Holding R3 - H3 incremental fits','SkeleCAD Holding R3 0.12 Support ON')

if __name__=='__main__':main()
