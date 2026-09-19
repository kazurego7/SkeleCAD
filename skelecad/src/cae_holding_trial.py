"""R2 ball-key bending comparison; not a spherical contact/preload simulation."""
import cae_retention_trial as shared

def main(config_key='joint_holding_trial'):
    c=shared.P[config_key]
    shared.C={**shared.C,**c};shared.OUT=shared.ROOT/c['output_directory']
    shared.main([v['label']+'_ball_key' for v in c['variants']])

if __name__=='__main__':
    import sys
    main(sys.argv[1] if len(sys.argv)>1 else 'joint_holding_trial')
