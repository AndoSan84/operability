import json, sys, inspect
sys.path.insert(0, '.')
from harness import parsers, maze_domain
V = maze_domain._vendor()
insts = {i['id']: i for i in json.load(open('instances_A_v4/maze_M2.json'))}
rows = [json.loads(l) for l in open('results_A_v4/results.jsonl')]
DRIVER = r'''
import inspect as _i, json as _j
_cands=[(n,f) for n,f in list(globals().items()) if callable(f) and getattr(f,'__module__',None)=='__main__' and not n.startswith('_') and _i.isfunction(f)]
_pref=[c for c in _cands if any(k in c[0].lower() for k in ('path','solve','bfs','maze'))] or _cands
_res=None
for _n,_f in _pref:
    _np=len(_i.signature(_f).parameters)
    _args={0:(),1:(MAZE,),2:(MAZE,(0,0)),3:(MAZE,(0,0),(S,S))}.get(_np)
    if _args is None: continue
    try:
        _r=_f(*_args)
    except Exception as e:
        continue
    if isinstance(_r,tuple) and _r and isinstance(_r[0],list): _r=_r[0]
    if isinstance(_r,list) and _r and isinstance(_r[0],(tuple,list)):
        _res=[tuple(x[:2]) for x in _r]; print('FUNC',_n); break
print('RESULT', _j.dumps(_res))
'''
out = []
for r in rows:
    if r['arm'] != 'm2_mental': continue
    inst = insts[r['instance_id']]
    code = parsers.extract_code(r['raw_response'], 'python')
    if code is None:
        out.append((r['instance_id'], 'no code', None)); continue
    s = inst['size'] - 1
    # strip top-level example calls that print / use input? keep code as is, guard __main__
    prog = f"MAZE = {json.dumps(inst['maze'])}\nmaze = MAZE\nS = {s}\n" + code.replace('if __name__ == "__main__":', 'if False:').replace("if __name__ == '__main__':", 'if False:') + DRIVER
    stdout, err = maze_domain.run_program(prog, timeout_s=60)
    res = None
    for line in stdout.splitlines():
        if line.startswith('RESULT '): res = json.loads(line[7:])
    if not res:
        out.append((r['instance_id'], 'no result: ' + (err or stdout[-200:] or '')[-160:].replace('\n', ' '), None)); continue
    ok, reason = V.validate_path(inst['maze'], inst['n_keys'], [tuple(x) for x in res])
    rep = maze_domain.extract_path(r['raw_response'])
    out.append((r['instance_id'], f"code {'VALID' if ok else 'invalid:'+str(reason)} len={len(res)} opt={inst['solution_length']} | reported len={len(rep) if rep else None} same_as_code={rep==[tuple(x) for x in res]}", ok))
for o in out: print(o[0], o[1])
print('code valid when executed:', sum(1 for o in out if o[2]), '/', len(out))
