import json,glob,csv,re,os
WATCH = r'(Bacillus (anthracis|cereus)|Yersinia|Francisella|Burkholderia|Brucella|Coxiella|Rickettsia|Orientia|Vibrio|Salmonella|Shigella|Clostrid|Mycobacterium|Corynebacterium diphth|Neisseria (meningitidis|gonorrhoeae)|Legionella|Listeria|Leptospira|Bordetella|Campylobacter|Helicobacter|Nocardia|Chlamydia|Candida auris|Cryptococcus|Histoplasma|Coccidioides|Blastomyces|Plasmodium|Toxoplasma|Cryptosporidium|Entamoeba|Giardia|Naegleria|Acanthamoeba|Balamuthia|Variola|Monkeypox|Orthopoxvirus|Ebola|Marburg|Nipah|Hendra|Lassa|Influenza|Coronavirus|SARS|MERS|Hantavirus|Dengue|Zika|Chikungunya|Rabies|Poliovirus|Enterovirus|Norovirus|Measles|Rubella|Varicella|Bacillus anthracis)'
rows=[]
for f in sorted(glob.glob('analysis/WBM*.json')):
    s=os.path.basename(f)[:6]
    g=json.load(open(f))
    for lvl in ('speciesData','subspeciesData'):
        for r in g['indentification_DNA'][lvl]['data']:
            rows.append(dict(sample=s,level=lvl,type=r['Type'],taxid=r['Taxid'],
                name=r['Scientific Name'],hi=r['Human Infection'],
                real=int(r['Real Read']),est=int(r['Estimate Read']),ab=float(r['Abundance'].rstrip('%'))))
with open('analysis/species_all.tsv','w',newline='') as fh:
    w=csv.DictWriter(fh,rows[0].keys(),delimiter='\t');w.writeheader();w.writerows(rows)

sp=[r for r in rows if r['level']=='speciesData']
print("### TOP 10 BY ABUNDANCE (species)")
for s in sorted(set(r['sample'] for r in sp)):
    ss=sorted([r for r in sp if r['sample']==s],key=lambda x:-x['ab'])
    print(s, ' | '.join(f"{r['name']} {r['ab']}%({r['real']})" for r in ss[:10]))
    print('   n_species=',len(ss),' types=',{t:sum(1 for r in ss if r['type']==t) for t in set(r['type'] for r in ss)})

print("\n### HUMAN-INFECTION FLAGGED (Y)")
for s in sorted(set(r['sample'] for r in sp)):
    ss=sorted([r for r in sp if r['sample']==s and r['hi']=='Y'],key=lambda x:-x['ab'])
    print(s,len(ss),'|',' ; '.join(f"{r['name']} {r['ab']}% r={r['real']}" for r in ss))

print("\n### WATCHLIST MATCHES (any abundance)")
for s in sorted(set(r['sample'] for r in sp)):
    ss=sorted([r for r in sp if r['sample']==s and re.search(WATCH,r['name'],re.I)],key=lambda x:-x['ab'])
    print(s,len(ss),'|',' ; '.join(f"{r['name']} {r['ab']}% r={r['real']} e={r['est']}" for r in ss))

print("\n### NON-BACTERIAL (virus/fungi/parasite/archaea)")
for s in sorted(set(r['sample'] for r in sp)):
    ss=sorted([r for r in sp if r['sample']==s and r['type']!='Bacteria'],key=lambda x:-x['ab'])
    print(s,len(ss),'|',' ; '.join(f"[{r['type']}] {r['name']} {r['ab']}% r={r['real']}" for r in ss))
