import csv, importlib.util, sys, contextlib, io, re, urllib.parse, json, os
from pathlib import Path

ROOT=Path(os.environ.get('NYTFT_WORK_ROOT','/mnt/data')).resolve()
EXHAUSTIVE_ROOT=Path(os.environ.get('NYTFT_EXHAUSTIVE_ROOT',str(ROOT/'nytft_exhaustive'))).resolve()
LEDGER=EXHAUSTIVE_ROOT/'nytft_output/https___www.newyorker.com_magazine_tables-for-two - source occurrence ledger.csv'
AUX=EXHAUSTIVE_ROOT/'nytft_output/https___www.newyorker.com_magazine_tables-for-two - auxiliary evidence.csv'
OUT=ROOT/'final_candidates_input.csv'
EVID=ROOT/'final_candidate_evidence.csv'

spec=importlib.util.spec_from_file_location('rv6',str(ROOT/'repair_v6.py'))
rv6=importlib.util.module_from_spec(spec);sys.modules[spec.name]=rv6
with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(rv6)
C=rv6.C
with LEDGER.open(encoding='utf-8-sig',newline='') as f: ledger_rows=list(csv.DictReader(f))
ledger_by_id={r['occurrence_id']:r for r in ledger_rows}
with AUX.open(encoding='utf-8-sig',newline='') as f: aux_rows=list(csv.DictReader(f))
aux_by_url={}
for r in aux_rows: aux_by_url.setdefault(r['source_url'].replace('http://','https://').rstrip('/'),[]).append(r)

# Source-name corrections keyed to occurrence IDs. These are derived from the same source block,
# not from current businesses occupying the address.
OV={
# Recent/multi-venue articles
'04853944b1a798d8':'One White Street','8b037ea70a2f1363':'The Usual','04c5cee0ed642ae0':'Risbo',
'a1e3764ee4314e33':'Lucia Pizza of Avenue X','8676788e87a102dd':"L’Antica Pizzeria da Michele",
'440041f5e50b8ac0':'Caleta','bc135bdb6b7268db':'Three Roosters Thai','1b3740a93b413988':'Three Roosters Thai',
'e04f2a2c881959cd':'Charles Pan-Fried Chicken','6a821b01bade9ec2':'Charles Pan-Fried Chicken',
'9b683eb6bafdc82d':'Congee Village','da34a3079610559f':'Congee Village',
'a0d0b17edb13227a':'Lucky Pickle','21970ab931ccceda':'Café Booqoo',
'4c8d3f800fdf6fed':'Gottino','20e812235123a70e':'Wilfie & Nell',
'f1f10c61f2b25689':'Sau Voi Corp.','4419799d0a3a91c6':'Baoguette/Pho Sure',
'92781733f9bbf304':'Shalizar','dbdacc3922e7fb32':'Ravagh',
'bae4346c127341db':'Flatbush Farm','ee9adc13224a8ce4':'The Farm on Adderley',
'649157f6bfe5c7b1':'Morimoto','718222ba55a2883c':'Buddakan',
# 1999-2004 OCR/source-header repairs
'23ad9d9ac60ef11d':'Bridge Cafe','dd363401bb5f2e23':'Palm Restaurant','59b9a2d7970a92bb':'Palm Restaurant',
'97e87cf771646c38':'Roettele A.G.','fd57af41766f5285':'Roettele A.G.','85d18bda6dcb89ca':'Roy’s',
'f0f97c90d9f0137f':'Roy’s','440e61dcc6332bc2':'The Red Cat','049da5fb783230ce':'The Red Cat',
'9db874bbcfbf18f8':'Quilty’s','b5ece16b345cf8e4':'Norma’s at Le Parker Meridien','69bd6951e0a36706':'Neo',
'24c32ffc397bbd5d':'Quercy','0851377da34d21d1':'Harry Cipriani','c5412f1682e67853':'Jewel Bako',
'0745f9f47ee03096':'Craft','cf2cfa7fe927e0e8':'One Fifth Avenue',
# Historical OCR/prose repairs
'2379a3c7d9930d98':'Hastings, Vernon, and Williams','fa662952b03e3ab5':'Jack White’s 18 Club',
'cbca452d9e8dc93f':'Polish Restaurant','c9441f50690e69e7':'Club Gaucho','2abb3a2e44499852':'El Chico',
'6998b3666322ae91':'Nick’s','f3cfd7cf3a31dc5a':'Larue','0aca89f2ec137355':'Nine O’Clock Club',
'4fbc14a9dd87f576':'Jack White’s Club 18','7da56e72c657963c':'Barney Gallant’s',
'3943638eec8f593c':'Mon Paris','b8dd01123a3822f8':'Daffydil','1ea52bf8dc607409':'Henry’s',
'ac410cc6a7913c14':'Ambassadeurs','b313dd9c6b97ae09':'Mijako Japanese Restaurant',
'b5dcc226962df4e8':'Chinese Delmonico’s','93a7949c151701fa':'Marcell',
'fc0ac6d73aa5c915':'Henry’s','30877b4053b8eb53':'Seven-Eleven Club',
'aafd702cd455c264':'Villa Venice','a0d1c549a22ea822':'Barney Gallant’s',
'2a0bc18178fae222':'The Florida','fa2047336adeb39a':'Art Studio Club',
'805d4fd84106c682':'Threefold Restaurant','d798f88d177fcf8c':'Garden Restaurant',
'f562967ca1becd5c':'Ka Lama O Hawaii','bcc993968b6cbcf3':'Club Chantee',
'0b278d5c5744e464':'Three Hundred Club','2c43d1bb064335a2':'Regent Club',
'b087e5cde4a8afb7':'Sardi’s','5a617eb66ed29c83':'Russiana',
'69c6cbe7859ca957':'Dickie Wells’','3bdcbae80234f79c':'Bali','e934ce800d31ccd8':'18 Club',
'614cc229a5dc8fc2':'Number Seventy Park Avenue','2e1091047040002c':'Yacht Club',
'026ccdf5cb598748':'Hamburger Mary’s','febfeaae817029cf':'Leon & Eddie’s',
'3ae93ddff8af73c8':'Tillie’s','9ed668be410bc191':'Place de l’Opera',
'6095e3f55dce8e85':'Maisonnette Russe de Paris','971603d85f4ed102':'Texas Guinan’s',
'a1e5a43ff7d8182e':'Owl Club','94f0101601ed13a4':'Forty-fifth Street Yacht Club',
'4ffd491baf0c3d3a':'Cameo','bfe668de231c65b4':'Enrico and Paglieri',
'baade0c9e8170d66':'New Caravan Club','55762edd85c26c8e':'Katinka',
'88240ce8516f6e5e':'Crest Room',
}

# Final source-text corrections from the local source-block audit.
OV.update({
'd9d1516ba960e9af':'The Mujako',
'b31d7b9ba7162823':'Mijako Japanese Restaurant',
'a3aedc1826b12d55':'El Gaucho',
'39436f4e73ba43ef':'Mon Paris',
'd22e57a718944612':'Nine O’Clock Club',
'efe672c6aae19599':'Nine O’Clock Club',
'0abf2d64cc1dac55':'Café Society Uptown',
'88240c86358e687f':'Crest Room',
'd63f897c46a09cbd':'One Fifth Avenue',
'cf2cfa1fea94c13e':'One Fifth Avenue',
'97a275ae3b84a1bb':'Neo',
'2625af2276a555f0':'Neo',
'dca93e0f97327f6d':'Quercy',
'c96e39f9fc18fef4':'Quercy',
'6766efaee41bb1b6':'70 Pine Street',
'cff35ecefd4fc906':'The Four Seasons',
'2d3052dd57412dc2':'Mayanoki',
'6718812d78012252':'Berber Street Food',
'de4c8e03bb99a62f':'Adda Indian Canteen',
'9eacffa98dd54ee6':'Una Pizza Napoletana',
'd5dfea8ef3a2c12b':'Harlem Hops',
'fbbc337157d8e59b':'Oxomoco',
'34dee4911113ef5f':'Chicha',
'1b754277025326e3':'Don Wagyu',
'0a0a59b4f5c54a5f':'Sofreh',
'8b037ea463c0defc':'The Usual',
'04c5cee88ad4cda2':'Risbo',
'aace1e1265ccd622':'Kopitiam',
'04853944b9be7128':'One White Street',
'ff62a70c7e492f0d':'Le B.',
'9db40b83ae34b1c7':'Quilty’s',
'd2b4190bfa685f32':'Quilty’s',
'c752f24285e59767':'Roettele A.G.',
'97e50ef9a8e01a5c':'Roettele A.G.',
'51d3e37d92d40dd6':'Roy’s',
'f0f97c90d9f0137f':'Roy’s',
'a0a86ed3f0840062':'The Red Cat',
'049da5fb783230ce':'The Red Cat',
'4eac809d40f45464':'Norma’s at Le Parker Meridien',
'734570dfd8a679e2':'Norma’s at Le Parker Meridien',
'085137a4018a3ca3':'Harry Cipriani',
'65a64768460b843b':'Sofreh',
'23ad542a2a2401b3':'Bridge Cafe',
'861a116bf4395e43':'Bridge Cafe',
'b22e1a490f2024f7':'Clinton St. Baking Company',
'dd363398aa5ce6e0':'Palm Restaurant',
'59b9b66aa92575d4':'Palm Restaurant',
'ac4dae47b050b17a':'Ambassadeurs',
'1ea01a9ddb3f6e78':'Henry’s',
'bcc99306f61b9952':'Club Chantee',
'bab9df38fd62d47e':'Ka Lama O Hawaii',
'6998ed512f259fa3':'Nick’s',
'7da475eef4ab3ee6':'Barney Gallant’s',
})
ADDRESS_OVERRIDES={
'e04f2a2c881959cd':'340 W 145th St',
}

DROP_IDS={
'49814d6a0ec3d37a', # 5 Pork Chops. Dr — prose, not an address
'5f35e1aa994d4ca4', # Three Owls Market — venue name parsed as address
'2af5f8ec026a485a', # 9 P.M. the Pl — prose
'0f5b40a4408e2eb0', # 1958 Jimmy St — year/name prose
'a21d3a33c8185271', # four Broadway m — OCR fragment
}

# Missing source-grounded complete addresses excluded by the first pass.
ADD={
'712b48d4578629f5':'Co.','cbcf4ee694b60ea1':'The New French','6d3cba882c204fe1':'15 East',
'65345d8595541be6':'No. 1 Chinese','ce2fafc7d5b0c2dd':'WD-50','a268655187677501':'RM',
'b7f30435f7c26e61':'Al Di Là','844aa086a06dd3ec':'Club Latino','b02fb88fe50265f5':'Ruban Bleu',
'd33fa4dac6032782':'Onyx Club','39b180fd4db7c0b0':'Barney Gallant’s','c19b1ec85334a6ae':'The Park Avenue',
'6eaddf595eb78934':'The Park Avenue','21d7b63df43304f1':'Le Perroquet de Paris',
'4fac863a64c551c8':'Schrafft’s Alexandria Room','d13fa3867356ac81':'Le Perroquet de Paris',
'94076677d12c549e':'Crillon Restaurant','510c1f5ebec0f60b':'Anavi’s Shish Kebab',
'c09179a54ecba851':'Maison Arthur','80a37531680477df':'Villa Venice',
'a0d0b17edb13227a':'Lucky Pickle',
}

# Special manually recovered article whose archive URL itself was malformed in the live listing.
DELLANIMA={
'occurrence_id':'manual-dellanima-2008','inventory_order':'','source_url':'https://www.newyorker.com/magazine/%25issue%25/dellanima',
'canonical_url':'https://www.newyorker.com/magazine/%25issue%25/dellanima','source_status':'200',
'guide':'Tables for Two','year':'2008','source_location':'metadata/auxiliary exact URL recovery','block_order':'0','occurrence_order':'1',
'pattern_type':'manual-source-recovery','address_completeness':'complete','candidate_name':'Dell’Anima','name_basis':'New Yorker article plus exact-source auxiliary record',
'raw_address':'38 Eighth Ave. at Jane St.','canonical_source_address':'38 8th Ave','evidence_excerpt':'Dell’Anima is identified in the source record at 38 Eighth Avenue at Jane Street.',
'auxiliary_provider':'The New Forker','auxiliary_name':'Dell’Anima','auxiliary_address':'38 Eighth Ave. at Jane St.','auxiliary_latitude':'40.7379298','auxiliary_longitude':'-74.0042856',
'auxiliary_place_id':'','auxiliary_google_maps_url':'','google_result_name':'','google_result_address':'','google_latitude':'','google_longitude':'','google_maps_url':'','google_categories':'',
'decision':'manual-source-recovery','verification_method':'exact-source-auxiliary-coordinate','address_type':'street_address','address_confidence':'high','name_confidence':'high','exclusion_reason':''
}

ORD_REPL={
'fiftyeighth':'58th','fiftysecond':'52nd','fiftyfirst':'51st','fiftyfourth':'54th','fiftyfifth':'55th','fiftysixth':'56th','fiftyseventh':'57th','fiftyninth':'59th',
'fortyeighth':'48th','fortyninth':'49th','fortyfourth':'44th','fortyfifth':'45th','fortysixth':'46th','fortyseventh':'47th',
'sixtieth':'60th','sixtyfirst':'61st','sixtysecond':'62nd','sixtythird':'63rd','sixtyfourth':'64th','sixtyfifth':'65th','sixtysixth':'66th','sixtyseventh':'67th','sixtyeighth':'68th','sixtyninth':'69th',
'thirtysixth':'36th','thirtysecond':'32nd','thirtyfirst':'31st','thirtyfourth':'34th','thirtyfifth':'35th','thirtyseventh':'37th','thirtyeighth':'38th','thirtyninth':'39th',
'twentysecond':'22nd','twentythird':'23rd','twentyfourth':'24th','twentyfifth':'25th','twentysixth':'26th','twentyseventh':'27th','twentyeighth':'28th','twentyninth':'29th',
}
def clean_address(a):
 a=C.canonical_address_text(a)
 for src,dst in ORD_REPL.items():
  a=re.sub(rf'\b{src}\b',dst,a,flags=re.I)
 # Normalize direction/suffix punctuation without lower-casing street names.
 a=re.sub(r'\b(East|West|North|South)\b',lambda m:{'east':'E','west':'W','north':'N','south':'S'}[m.group(1).lower()],a,flags=re.I)
 a=re.sub(r'\b(St|Ave|Rd|Pl|Blvd|Pkwy|Dr|Ln|Ct|Ter|Hwy)\.',r'\1',a,flags=re.I)
 a=re.sub(r'\bMcdougal\b','MacDougal',a,flags=re.I)
 a=re.sub(r'\bAve X\b','Avenue X',a,flags=re.I)
 a=re.sub(r'\s+',' ',a)
 return a.strip(' ,.;')

def plausible_coords(lat,lon):
 try: lat=float(lat); lon=float(lon); return -90<=lat<=90 and -180<=lon<=180
 except: return False

def nyc_coords(lat,lon):
 try: lat=float(lat);lon=float(lon);return 40.45<=lat<=40.95 and -74.30<=lon<=-73.65
 except:return False

def strict_addr_agree(a,b):
 try:return C.address_similarity(a,b)[0]
 except:return False

def full_postal(a):
 return bool(re.search(r'\b\d{5}(?:-\d{4})?\b',a or '') and re.search(r'\b(?:United States|USA)\b',a or '',re.I))

def classify(name,evidence):
 if name=='70 Pine Street': return 5,'Landmark'
 t=(name+' '+evidence).casefold()
 if 'new york galleries' in t or re.search(r'\b(?:museum|gallery|theatre|theater|archive|cultural institution)\b',t): return 3,'Cultural institution'
 if re.search(r'\b(?:night club|nightclub|cabaret|dance club|dancing|revue|bowling|billiards|yacht club|roof garden|supper club)\b',t) or name.casefold().startswith('club '): return 4,'Nightlife / activity'
 if re.search(r'\b(?:bookshop|bookstore|grocer|grocery|marketplace|retail shop|food shop|dashi shop)\b',t) and not re.search(r'\b(?:restaurant|café|cafe|bar|diner|bakery)\b',t): return 2,'Shop'
 if re.search(r'\b(?:hotel|lodging|hostel|resort)\b',t) and not re.search(r'\b(?:restaurant|dining|dinner|lunch|bar|café|cafe)\b',t): return 6,'Hotel'
 if re.search(r'\b(?:landmark|monument|historic site|viewpoint)\b',t): return 5,'Landmark'
 if 'wine bar' in t:return 1,'Wine bar'
 if re.search(r'\b(?:bar|tavern|pub|saloon)\b',t):return 1,'Bar'
 if re.search(r'\b(?:café|cafe|coffee shop|tea room)\b',t):return 1,'Café'
 if re.search(r'\b(?:bakery|ice cream|gelato|dessert)\b',t):return 1,'Food and drink venue'
 return 1,'Restaurant'

# Build from V6 source-grounded candidates.
items=[]
for r,name,conf,nb,addr,auxfull,ab in rv6.consider:
 if r['occurrence_id'] in DROP_IDS: continue
 name=OV.get(r['occurrence_id'],name)
 addr=clean_address(ADDRESS_OVERRIDES.get(r['occurrence_id'],addr))
 if not name or not addr: continue
 items.append((dict(r),name,addr,conf,nb,auxfull,ab))
# Add source-grounded exclusions manually recovered.
for oid,name in ADD.items():
 r=ledger_by_id.get(oid)
 if not r: continue
 addr=clean_address(r.get('canonical_source_address') or r.get('raw_address'))
 items.append((dict(r),name,addr,'high','manual source-block correction',r.get('auxiliary_address',''),'manual source recovery'))
items.append((dict(DELLANIMA),'Dell’Anima','38 8th Ave','high','manual source/article recovery','38 Eighth Ave. at Jane St.','manual source recovery'))

# Consolidate exact source identity/address pairs while retaining every occurrence in evidence ledger.
by_key={}; evidence=[]
for r,name,addr,conf,nb,auxfull,ab in items:
 key=(rv6.nid(name),C.norm_address(addr))
 if not all(key): continue
 evidence.append({'Candidate Key':' | '.join(key),'Occurrence ID':r.get('occurrence_id',''),'Name':name,'Source Address':addr,'Source URL':r.get('source_url',''),'Guide':r.get('guide',''),'Year':r.get('year',''),'Evidence Excerpt':r.get('evidence_excerpt',''),'Name Basis':nb,'Address Basis':ab})
 # choose newest archive occurrence; inventory order is ascending newest-first where available.
 rank=(int(r.get('inventory_order') or 10**9),int(r.get('occurrence_order') or 10**9),r.get('source_url',''))
 if key not in by_key or rank<by_key[key][0]: by_key[key]=(rank,(r,name,addr,conf,nb,auxfull,ab))

rows=[]
for key,(_,payload) in sorted(by_key.items(),key=lambda kv:(int(kv[1][1][0].get('year') or 9999),kv[1][1][1].casefold(),kv[1][1][2].casefold())):
 r,name,addr,conf,nb,auxfull,ab=payload
 bucket,cat=classify(name,r.get('evidence_excerpt',''))
 # choose trustworthy coordinate evidence if already exact; otherwise remote re-geocode.
 reuse='no'; reuse_basis=''; lat=lon=full=''; existing_url=''
 aux_addr=clean_address(r.get('auxiliary_address','')) if r.get('auxiliary_address') else ''
 if plausible_coords(r.get('auxiliary_latitude'),r.get('auxiliary_longitude')) and (not aux_addr or strict_addr_agree(addr,aux_addr)):
  lat,lon=r.get('auxiliary_latitude',''),r.get('auxiliary_longitude',''); full=r.get('google_result_address','') if full_postal(r.get('google_result_address','')) and strict_addr_agree(addr,r.get('google_result_address','')) else ''
  reuse_basis='exact-source auxiliary coordinates'; existing_url=r.get('auxiliary_google_maps_url','') or r.get('google_maps_url','')
  if full: reuse='yes'
 elif plausible_coords(r.get('google_latitude'),r.get('google_longitude')) and strict_addr_agree(addr,r.get('google_result_address','')):
  if nyc_coords(r.get('google_latitude'),r.get('google_longitude')) or name=='Blue Hill at Stone Barns':
   lat,lon=r.get('google_latitude',''),r.get('google_longitude',''); full=r.get('google_result_address','');existing_url=r.get('google_maps_url','')
   reuse_basis='existing exact-address Google result'
   if full_postal(full): reuse='yes'
 # explicit locality hint for the one clearly non-NYC source.
 location_hint='Pocantico Hills, New York, United States' if name=='Blue Hill at Stone Barns' else 'New York, NY, United States'
 desc=f'The New Yorker source reviews or profiles {name} at this address.'
 rows.append({
  'Candidate ID':f'cand-{len(rows)+1:04d}','Name':name,'Source Address':addr,'Guide':r.get('guide') or 'Tables for Two',
  'Source URL':r.get('source_url',''),'Source Status':str(r.get('source_status','')),'Priority':str(r.get('occurrence_order') or 1),'Year':str(r.get('year') or ''),
  'Category Hint':cat,'Bucket Hint':bucket,'Description':desc,'Evidence Excerpt':r.get('evidence_excerpt',''),
  'Occurrence ID':r.get('occurrence_id',''),'Location Hint':location_hint,'Reuse Approved':reuse,'Reuse Basis':reuse_basis,
  'Existing Full Address':full,'Existing Latitude':lat,'Existing Longitude':lon,'Existing Google Maps URL':existing_url,
  'Original Google Name':r.get('google_result_name',''),'Original Google Address':r.get('google_result_address',''),
  'Original Google Categories':r.get('google_categories',''),'Original Official Website':r.get('google_official_website',''),
  'Original Official Website Check':r.get('official_website_check',''),'Original Google Verification Status':r.get('google_verification_status',''),
  'Original Verification Method':r.get('verification_method',''),'Original Google Match Basis':r.get('google_match_basis',''),
  'Auxiliary Provider':r.get('auxiliary_provider',''),
  'Auxiliary Address':r.get('auxiliary_address',''),'Auxiliary Latitude':r.get('auxiliary_latitude',''),'Auxiliary Longitude':r.get('auxiliary_longitude',''),
  'Name Basis':nb,'Address Basis':ab,
 })

fields=list(rows[0].keys())
with OUT.open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
with EVID.open('w',encoding='utf-8-sig',newline='') as f:
 flds=list(evidence[0].keys());w=csv.DictWriter(f,fieldnames=flds);w.writeheader();w.writerows(evidence)
print(json.dumps({'candidate_rows':len(rows),'evidence_occurrences':len(evidence),'reuse_approved':sum(r['Reuse Approved']=='yes' for r in rows),'needs_remote_geocode':sum(r['Reuse Approved']!='yes' for r in rows),'buckets':{str(b):sum(int(r['Bucket Hint'])==b for r in rows) for b in range(1,7)}},indent=2,ensure_ascii=False))
