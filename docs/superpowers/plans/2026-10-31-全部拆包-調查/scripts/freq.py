import json,sys,io,re,collections,subprocess
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
owner=json.load(open('tmp_master/owner.json',encoding='utf-8'))
txt=open('tmp_master/engine_log.txt',encoding='utf-8',errors='replace').read().splitlines()
commits=collections.defaultdict(set)
cur=None
hdr=re.compile(r'^@@ .*? @@ ?(\w+)?')
dl=re.compile(r'^[+-]    def (\w+)')
for line in txt:
    if line.startswith('@@COMMIT'):
        cur=line.split()[1]; continue
    m=hdr.match(line)
    if m and cur:
        if m.group(1): commits[cur].add(m.group(1))
        continue
    m=dl.match(line)
    if m and cur: commits[cur].add(m.group(1))
pk=collections.Counter()
for c,ms in commits.items():
    ps=set(owner.get(m,'?') for m in ms)
    for p in ps: pk[p]+=1
# module files per package
mods=collections.defaultdict(set)
pat=re.compile(r'tianxia/[A-Za-z0-9_/]+\.py')
NORM={'tavern':'features/tavern','smithy':'features/smithy','gear':'features/gear','outlets':'features/outlets','arts':'features/arts','craft':'features/craft','sense':'features/sense','features/challenge':'features/figures'}
for a in ['core','action','combat','growth','world']:
    d=json.load(open(f'area_{a}.json',encoding='utf-8'))
    for p,pv in d['assign'].items():
        p=NORM.get(p,p)
        for n in pv.get('modules',[]):
            for f in pat.findall(n):
                if f!='tianxia/engine.py': mods[p].add(f)
mods['features/battle'].add('tianxia/siege.py')
wt='../splitwt'
mc={}
for p,fs in mods.items():
    if p=='core' or not fs: continue
    out=subprocess.run(['git','-C',wt,'log','--since=2026-10-16','--no-merges','--format=%h','--']+sorted(fs),capture_output=True,text=True).stdout.split()
    mc[p]=set(out)
# combined unique commits: engine commits touching pkg + module commits
eng=collections.defaultdict(set)
for c,ms in commits.items():
    for p in set(owner.get(m,'?') for m in ms): eng[p].add(c)
rows=[]
for p in sorted(set(list(eng)+list(mc))):
    rows.append((p,len(eng.get(p,())),len(mc.get(p,())),len(eng.get(p,set())|set(x[:7] for x in mc.get(p,set())))))
for r in sorted(rows,key=lambda r:-r[3]): print(r)
print('engine commits',len(commits))
