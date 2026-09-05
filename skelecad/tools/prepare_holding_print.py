"""Three C4 holding-fit variants, thick stems, no additional mouth relief."""
import prepare_retention_print as shared

def main():
    c=shared.PARAMS['joint_holding_trial'];shared.C={**shared.C,**c}
    shared.BASE=shared.ROOT/c['output_directory']
    names=[v['label']+suffix for v in c['variants'] for suffix in ('_socket','_ball_key')]
    shared.main(names,'Holding R2 - 3 C4 fits','SkeleCAD Holding R2 0.12 Support ON')

if __name__=='__main__':main()
