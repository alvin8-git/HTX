import re,json,sys,os
def extract(path):
    s=open(path,encoding='utf-8',errors='replace').read()
    i=s.find('globalData:{')
    st=s.index('{',i)
    d=0
    for j in range(st,len(s)):
        c=s[j]
        if c=='"':  # skip string
            k=j+1
            while True:
                if s[k]=='\\': k+=2; continue
                if s[k]=='"': break
                k+=1
            continue
        if c=='{': d+=1
        elif c=='}':
            d-=1
            if d==0: return json.loads(s[st:j+1])
    raise ValueError('unbalanced')
if __name__=='__main__':
    for f in sys.argv[1:]:
        g=extract(f)
        out='analysis/'+os.path.basename(f).replace('_en.html','.json')
        json.dump(g,open(out,'w'))
        print(os.path.basename(f), list(g.keys()))
