import gzip,os,csv,json,collections
from concurrent.futures import ProcessPoolExecutor
def stat(a):
    s,name,p=a
    r=[]
    with gzip.open(p,'rt') as f:
        for i,l in enumerate(f):
            if i%4==1: r.append(l.strip())
    if not r: return s,name,0,0,0.0
    gc=sum((x.count('G')+x.count('C')) for x in r)/sum(len(x) for x in r)
    return s,name,len(r),len(set(r)),gc*100
rows=[r for r in csv.DictReader(open('analysis/species_all.tsv'),delimiter='\t') if r['level']=='speciesData']
tasks=[]
for r in rows:
    n=r['name'].replace(' ','_').replace('/','_')
    p=f"{r['sample']}/ExtractRead_DNA/Species/{n}/{n}_1.fq.gz"
    if os.path.exists(p): tasks.append((r['sample'],r['name'],p))
out={}
with ProcessPoolExecutor(16) as ex:
    for s,nm,n,u,gc in ex.map(stat,tasks,chunksize=20): out[s+'|'+nm]=dict(n=n,uniq=u,gc=round(gc,1))
json.dump(out,open('analysis/dedup.json','w'))
print('done',len(out))
