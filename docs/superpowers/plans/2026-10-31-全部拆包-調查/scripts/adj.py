import json,sys,io,collections,itertools
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
inv=json.load(open('inventory.json',encoding='utf-8'))
owner=json.load(open('tmp_master/owner.json',encoding='utf-8'))
ms=sorted(inv['game_methods'],key=lambda m:m['start'])
adj=collections.Counter()
for a,b in zip(ms,ms[1:]):
    pa,pb=owner[a['name']],owner[b['name']]
    if pa!=pb and pa not in('core',) and pb not in ('core',):
        adj[tuple(sorted((pa,pb)))]+=1
# 每包的「段數」：連續同主人的區段有幾段
seg=collections.Counter()
prev=None
for m in ms:
    p=owner[m['name']]
    if p!=prev: seg[p]+=1
    prev=p
print('segments per package:',sorted(seg.items(),key=lambda x:-x[1]))
print('adjacent pairs (non-core):')
for k,v in sorted(adj.items(),key=lambda x:-x[1]): print(' ',k,v)
json.dump({'|'.join(k):v for k,v in adj.items()},open('tmp_master/adj.json','w',encoding='utf-8'),ensure_ascii=False)
