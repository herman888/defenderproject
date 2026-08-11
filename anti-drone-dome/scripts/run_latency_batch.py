"""Run the Day-2 latency sequence without per-mode operator intervention."""
from __future__ import annotations

import argparse, json, subprocess, sys
from pathlib import Path

from bench_common import metadata, write_artifact

ROOT = Path(__file__).resolve().parent.parent
MODES = ((1920,1080,"MJPG",30.0,"1080p_initial"),(640,480,"YUY2",30.0,"640p_yuy2"),(1280,720,"MJPG",30.0,"720p_mjpg"),(1920,1080,"MJPG",30.0,"1080p_drift"))

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--monitor-resolution',required=True); p.add_argument('--refresh-hz',type=float,required=True); p.add_argument('--room-condition',required=True); p.add_argument('--stimulus-display',default=r'\\.\DISPLAY2'); p.add_argument('--trials',type=int,default=50); args=p.parse_args()
    runs=[]
    for w,h,fpsfmt,fps,label in MODES:
        cmd=[sys.executable,str(ROOT/'scripts'/'bench_camera.py'),'latency','--width',str(w),'--height',str(h),'--format',fpsfmt,'--fps',str(fps),'--trials',str(args.trials),'--stimulus-display',args.stimulus_display,'--preflight-seconds','2','--monitor-resolution',args.monitor_resolution,'--refresh-hz',str(args.refresh_hz),'--room-condition',args.room_condition,'--camera-rigid','--focus-locked','--vrr-status','NOT MEASURED','--motion-smoothing-status','NOT MEASURED','--power-saving-status','NOT MEASURED','--other-apps-closed','--windows-high-performance']
        result=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)
        paths=[line.strip() for line in result.stdout.splitlines() if 'artifacts' in line and line.strip().endswith('.json')]
        runs.append({'label':label,'command':cmd,'returncode':result.returncode,'artifact':paths[-1] if paths else 'NOT MEASURED','stderr':result.stderr[-1000:]})
    values=[]
    for run in runs:
        if run['artifact']!='NOT MEASURED':
            d=json.loads(Path(run['artifact']).read_text()); run['status']=d['measurement_status']; run['p50_ms']=d['statistics_ms']['p50']; run['successful_trials']=d['successful_trials']; values.append(run)
    first,next640,next720,last = runs
    drift = 'NOT MEASURED' if not isinstance(first.get('p50_ms'),(int,float)) or not isinstance(last.get('p50_ms'),(int,float)) else abs(last['p50_ms']-first['p50_ms'])/first['p50_ms']
    summary={'schema':'larp.camera-bench.v1','operation':'latency_batch_day2',**metadata(ROOT,{'monitor_resolution':args.monitor_resolution,'refresh_hz':args.refresh_hz,'modes':MODES}),'runs':runs,'checks':{'all_minimum_crossings':all(r.get('successful_trials',0)>=45 for r in runs),'drift_fraction':drift,'drift_over_15_percent':drift!='NOT MEASURED' and drift>.15,'640_not_lower_than_1080':isinstance(next640.get('p50_ms'),(int,float)) and isinstance(first.get('p50_ms'),(int,float)) and next640['p50_ms']>=first['p50_ms']}}
    print(write_artifact(ROOT,'camera','latency_batch',summary)); return 0
if __name__=='__main__': raise SystemExit(main())
