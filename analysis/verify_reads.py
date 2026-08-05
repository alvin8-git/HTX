import gzip,os,csv,sys,collections
from concurrent.futures import ProcessPoolExecutor
def count(p):
    n=0
    with gzip.open(p,'rb') as f:
        for i,_ in enumerate(f): n=i+1
    return n//4
def job(a):
    s,name,p=a
    return s,name,count(p)
tasks=[]
for s in ['WBM156','WBM174','WBM179','WBM185','WBM232']:
    d=f'{s}/ExtractRead_DNA/Species'
    for name in os.listdir(d):
        p=f'{d}/{name}/{name}_1.fq.gz'
        if os.path.exists(p): tasks.append((s,name,p))
print('dirs',len(tasks),flush=True)
res={}
with ProcessPoolExecutor(16) as ex:
    for s,name,n in ex.map(job,tasks,chunksize=20): res[(s,name)]=n
rep={}
for r in csv.DictReader(open('analysis/species_all.tsv'),delimiter='\t'):
    if r['level']=='speciesData': rep[(r['sample'],r['name'].replace(' ','_').replace('/','_'))]=int(r['real'])
mis=[]
for k,n in res.items():
    if k not in rep: mis.append((k,'NO_REPORT',n)); continue
    if rep[k]!=n: mis.append((k,rep[k],n))
print('matched',sum(1 for k in res if k in rep and rep[k]==res[k]),'/',len(res))
print('mismatches',len(mis))
for m in mis[:40]: print('  ',m)
import json;json.dump({f'{a}|{b}':c for (a,b),c in res.items()},open('analysis/readcounts.json','w'))
