#!/usr/bin/env python3
from __future__ import annotations
import csv, dataclasses, datetime as dt, hashlib, html, json, os, re, sys, time, unicodedata, urllib.parse, zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

GUIDE='https://www.newyorker.com/magazine/tables-for-two'
LABEL='https___www.newyorker.com_magazine_tables-for-two'
OUT=Path(os.environ.get('OUTPUT_DIR','newyorker_tables_for_two_audit')).resolve(); OUT.mkdir(parents=True, exist_ok=True)
START=dt.datetime.now(dt.timezone.utc)
UA='Mozilla/5.0 (compatible; TablesForTwoAudit/2026.08; +https://github.com/arthurfouray/af)'
HDR=['Name','Address','Latitude and longitude','Guide','Category','Description','Source URL','Priority','Year','Google Maps URL']
BUCKETS={1:'1. Restaurants, bars, caves.csv',2:'2. Shopping and food shops.csv',3:'3. Museum and Culture.csv',4:'4. Party, leisure, activities and other.csv',5:'5. Sightseeing.csv',6:'6. Hotels.csv'}
GENERIC={norm for norm in ['tables for two','tables for two the new yorker','new spot','the language barrier','three in one','hard workers','all new','on her own']}
STOP={'the','a','an','restaurant','cafe','café','bar','club','hotel','grill','house','kitchen','room','at','and','of','new','york'}
SUF=r'Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Lane|Ln\.?|Drive|Dr\.?|Place|Pl\.?|Court|Ct\.?|Highway|Hwy\.?|Parkway|Pkwy\.?|Terrace|Ter\.?|Way|Alley|Broadway|Bowery|Concourse|Turnpike|Route|Plaza|Square|Pier|Market|Mews|Crescent|Circle|Row|Walk'
TOK=r"[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9'’&.\-/]*"
DIR=r'(?:(?:N|S|E|W)\.?\s+|(?:North|South|East|West)\s+)?'
STCORE=rf'{DIR}(?:{TOK}\s+){{0,8}}(?:{SUF})'
INTL=r'rue|quai|avenue|boulevard|via|viale|piazza|calle|carrer|strada|straße|strasse|platz|weg|gasse|chome|dori|hutong|chemin|cours|passage|allée|allee|promenade|rua|avenida|paseo'
HOUSE=r'one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred'
ORD=r'first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|nineteenth|twentieth|thirtieth|fortieth|fiftieth|sixtieth|seventieth|eightieth|ninetieth|hundredth|twenty[- ]first|twenty[- ]second|twenty[- ]third|twenty[- ]fourth|twenty[- ]fifth|twenty[- ]sixth|twenty[- ]seventh|twenty[- ]eighth|twenty[- ]ninth|thirty[- ]first|thirty[- ]second|thirty[- ]third|thirty[- ]fourth|thirty[- ]fifth|thirty[- ]sixth|thirty[- ]seventh|thirty[- ]eighth|thirty[- ]ninth|forty[- ]first|forty[- ]second|forty[- ]third|forty[- ]fourth|forty[- ]fifth|forty[- ]sixth|forty[- ]seventh|forty[- ]eighth|forty[- ]ninth|fifty[- ]first|fifty[- ]second|fifty[- ]third|fifty[- ]fourth|fifty[- ]fifth|fifty[- ]sixth|fifty[- ]seventh|fifty[- ]eighth|fifty[- ]ninth|sixty[- ]first|sixty[- ]second|sixty[- ]third|sixty[- ]fourth|sixty[- ]fifth|sixty[- ]sixth|sixty[- ]seventh|sixty[- ]eighth|sixty[- ]ninth'
ADDR_PAT=[('us_numeric','complete',re.compile(rf'(?<![\w/])(?:No\.?\s*)?\d{{1,5}}(?:-\d{{1,5}})?[A-Za-z]?(?:\s*½)?\s+{STCORE}(?:\s*,?\s*(?:at|near|between|and|corner of|off)\s+{STCORE})?(?:\s*,?\s*(?:Brooklyn|Queens|Bronx|Manhattan|Staten Island|New York City|New York|NYC|Jersey City|Hoboken|Long Island City|Flushing|Astoria|Harlem))?(?:\s*,?\s*(?:NY|New York|NJ|New Jersey)\s*\d{{5}}(?:-\d{{4}})?)?',re.I)),('spelled_house','complete',re.compile(rf'(?<!\w)(?:{HOUSE})(?:[- ](?:{HOUSE})){{0,4}}\s+{STCORE}',re.I)),('ordinal_street','complete',re.compile(rf'(?<![\w/])\d{{1,5}}(?:-\d{{1,5}})?[A-Za-z]?(?:\s*½)?\s+{DIR}(?:{ORD})\s+(?:Street|Avenue|Road|Place|Lane|Drive|Boulevard)\b',re.I)),('intl_numeric','complete',re.compile(rf'(?<!\w)\d{{1,5}}(?:[-/]\d{{1,5}})?\s+(?:{INTL})\s+(?:{TOK}\s*){{1,10}}',re.I)),('intl_reversed','complete',re.compile(rf'(?<!\w)(?:{INTL})\s+(?:{TOK}\s+){{1,9}}\d{{1,5}}(?:[-/]\d{{1,5}})?\b',re.I)),('partial_location','partial',re.compile(rf'\b(?:at|on|near|opposite|across from|corner of|between|off)\s+(?:the\s+)?{STCORE}(?:\s*,?\s*(?:and|at|near|between)\s+{STCORE})?',re.I))]
PHONE=re.compile(r'(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}|\(\d{3}\)[ .-]?\d{3}[ .-]\d{4}')
ARTICLE_PATH=re.compile(r'^/(?:magazine/(?:\d{4}(?:/\d{2}/\d{2}|-\d{2}-\d{2})|%issue%|%25issue%25)/[^/?#]+|culture/the-food-scene/[^/?#]+)$',re.I)
ADDR_CUE=re.compile(rf'\b(?:{SUF}|{INTL}|address|located at|location)\b|\b\d{{1,5}}\s+(?:{TOK}\s+){{0,5}}(?:{SUF})\b',re.I)

def clean(s:Any)->str: return re.sub(r'\s+',' ',html.unescape(str(s or ''))).strip()
def fold(s:Any)->str: return ''.join(c for c in unicodedata.normalize('NFKD',str(s or '')) if not unicodedata.combining(c))
def nid(s:Any)->str:
    x=re.sub(r'[^a-z0-9]+',' ',fold(s).lower().replace('&',' and ')); return ' '.join(t for t in x.split() if t not in STOP)
def naddr(s:Any)->str:
    x=' '+fold(s).lower()+' '
    for a,b in {' street ':' st ',' avenue ':' ave ',' road ':' rd ',' boulevard ':' blvd ',' place ':' pl ',' drive ':' dr ',' lane ':' ln ',' court ':' ct ',' terrace ':' ter ',' parkway ':' pkwy ',' highway ':' hwy ',' united states of america ':' united states '}.items(): x=x.replace(a,b)
    return ' '.join(re.sub(r'[^a-z0-9]+',' ',x).split())
def sha(p:Path)->str:
    h=hashlib.sha256(); f=p.open('rb')
    for b in iter(lambda:f.read(1048576),b''): h.update(b)
    f.close(); return h.hexdigest()
def write_csv(path, fields, rows):
    rows=list(rows)
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows([{k:r.get(k,'') for k in fields} for r in rows])
    return len(rows)
def year_from(url,pub=''):
    if re.match(r'^\d{4}',pub or ''): return str(pub)[:4]
    m=re.search(r'/magazine/(\d{4})[/-]',url); return m.group(1) if m else ''
def slug_name(url):
    slug=urllib.parse.urlparse(url).path.rstrip('/').split('/')[-1]
    if slug.startswith('tables-for-two'): return ''
    slug=re.sub(r'^(?:restaurant-review-|tables-for-two-)','',slug)
    return ' '.join(w.capitalize() for w in slug.split('-') if w)
def title_name(t):
    t=clean(re.sub(r'\s+\|\s+The New Yorker$','',t or ''))
    t=re.sub(r'(?i)^restaurant review:\s*','',t)
    if nid(t) in GENERIC or not nid(t): return ''
    return t[:120]

def session():
    s=requests.Session(); s.headers.update({'User-Agent':UA,'Accept-Language':'en-US,en;q=0.8'})
    retry=Retry(total=3,connect=3,read=3,status=3,backoff_factor=.7,status_forcelist=[408,425,429,500,502,503,504],allowed_methods=['GET'])
    s.mount('https://',HTTPAdapter(max_retries=retry)); return s
S=session(); FETCH=[]; LAST=defaultdict(float)
def get(url,purpose,delay=.15,timeout=30):
    host=urllib.parse.urlparse(url).netloc; wait=delay-(time.monotonic()-LAST[host])
    if wait>0: time.sleep(wait)
    t=time.time(); err=''; r=None
    try: r=S.get(url,timeout=timeout,allow_redirects=True); status=r.status_code; txt=r.text if 'text' in r.headers.get('content-type','') or 'json' in r.headers.get('content-type','') else ''
    except Exception as e: status=0; txt=''; err=f'{type(e).__name__}: {e}'
    LAST[host]=time.monotonic(); FETCH.append({'requested_url':url,'final_url':getattr(r,'url',''),'status':status,'redirected':bool(r and r.url.rstrip('/')!=url.rstrip('/')),'content_type':getattr(r,'headers',{}).get('content-type','') if r else '', 'bytes':len(getattr(r,'content',b'')) if r else 0,'elapsed_ms':round((time.time()-t)*1000),'purpose':purpose,'error':err})
    return r,txt,status

def article_links(ht):
    soup=BeautifulSoup(ht,'lxml'); out=[]
    for a in soup.find_all('a',href=True):
        href=a['href'].split('#')[0]
        if href.startswith('/'): u='https://www.newyorker.com'+href
        else: u=href
        p=urllib.parse.urlparse(u)
        if p.netloc not in ('www.newyorker.com','newyorker.com'): continue
        path=urllib.parse.unquote(p.path.rstrip('/'))
        if ARTICLE_PATH.match(path) and '/magazine/tables-for-two' not in path:
            u='https://www.newyorker.com'+path
            if u not in out: out.append(u)
    return out

def discover():
    rows=[]; inv=[]; seen=set()
    for page in range(0,260):
        url=GUIDE if page==0 else f'{GUIDE}?page={page}'
        r,txt,st=get(url,'archive-pagination',.25)
        links=article_links(txt) if st==200 else []
        new=0
        if page!=0:
            for u in links:
                if u not in seen: seen.add(u); inv.append(u); new+=1
        rows.append({'page':page,'requested_url':url,'final_url':getattr(r,'url',''),'status':st,'article_links_detected':len(links),'new_unique_editorial_urls':new,'terminal':st==404 or (page>1 and st==200 and not links),'note':'page zero audited as alias' if page==0 else ''})
        if page>1 and (st==404 or (st==200 and not links)): break
    return inv,rows

def meta(soup,*names):
    for n in names:
        tag=soup.find('meta',attrs={'property':n}) or soup.find('meta',attrs={'name':n})
        if tag and tag.get('content'): return clean(tag['content'])
    return ''
def json_objs(x):
    if isinstance(x,dict):
        yield x
        for v in x.values(): yield from json_objs(v)
    elif isinstance(x,list):
        for v in x: yield from json_objs(v)

def parse_article(url,idx):
    r,txt,st=get(url,'editorial-article',.08)
    rec={'inventory_order':idx,'source_url':url,'canonical_url':getattr(r,'url',url),'status':st,'title':'','published':'','year':year_from(url),'content_blocks_inspected':0,'raw_address_occurrences':0,'error':''}
    blocks=[]
    if st!=200:
        rec['error']='non-200 fetch'; return rec,blocks
    soup=BeautifulSoup(txt,'lxml')
    can=soup.find('link',rel=lambda v:v and 'canonical' in v); rec['canonical_url']=can.get('href') if can else url
    title=meta(soup,'og:title','twitter:title') or clean(soup.title.get_text(' ')) if soup.title else ''
    desc=meta(soup,'og:description','twitter:description','description')
    pub=meta(soup,'article:published_time')
    rec.update({'title':title,'published':pub,'year':year_from(url,pub)})
    order=0
    if desc: blocks.append({'location':'metadata_description','order':order,'text':desc}); order+=1
    if title: blocks.append({'location':'metadata_title','order':order,'text':title}); order+=1
    for script in soup.find_all('script',attrs={'type':'application/ld+json'}):
        raw=script.string or script.get_text() or ''
        try: data=json.loads(raw)
        except Exception: continue
        for o in json_objs(data):
            if not rec['published'] and isinstance(o.get('datePublished'),str): rec['published']=o['datePublished']; rec['year']=year_from(url,o['datePublished'])
            if isinstance(o.get('headline'),str) and not title: title=clean(o['headline']); rec['title']=title
            if isinstance(o.get('articleBody'),str):
                for part in re.split(r'\\n|\n',o['articleBody']):
                    part=clean(part)
                    if len(part)>20: blocks.append({'location':'jsonld_articleBody','order':order,'text':part}); order+=1
    for tag in soup.find_all(['h1','h2','h3','p','figcaption','li']):
        txt2=clean(tag.get_text(' ',strip=True))
        if len(txt2)<12: continue
        cls=' '.join(tag.get('class',[]))
        if tag.name.startswith('h') or tag.find_parent('article') or 'body' in cls or 'paywall' in cls or tag.name=='figcaption':
            blocks.append({'location':f'html_{tag.name}','order':order,'text':txt2}); order+=1
    ded=[]; seen=set()
    for b in blocks:
        if b['text'] not in seen: seen.add(b['text']); ded.append(b)
    rec['content_blocks_inspected']=len(ded)
    return rec,ded

def find_addrs(text):
    hits=[]; occupied=[]
    for typ,comp,pat in ADDR_PAT:
        for m in pat.finditer(text):
            a,b=m.span(); raw=clean(m.group(0)).strip(' ,;:.()')
            if len(raw)<5 or any(max(a,x)<min(b,y) for x,y in occupied): continue
            occupied.append((a,b)); hits.append({'pattern_type':typ,'address_completeness':comp,'raw_address':raw,'start':a,'end':b})
    return sorted(hits,key=lambda h:h['start'])
def name_from(block,address,title,url,auxname=''):
    if auxname: return auxname,'auxiliary exact URL name'
    text=block or ''
    for pat in [rf"(?P<n>[A-Z][A-Za-z0-9À-ÖØ-öø-ÿ&’'./ -]{{1,90}}?),?\s+(?:is|was|opened|reopened|has opened|has reopened|moved|located)\s+(?:at|to|on)\s+{re.escape(address)}", rf"(?P<n>[A-Z][A-Za-z0-9À-ÖØ-öø-ÿ&’'./ -]{{1,90}}?),?\s+(?:at|on)\s+{re.escape(address)}"]:
        m=re.search(pat,text,re.I)
        if m:
            n=clean(m.group('n')); n=re.sub(r'(?i)^(?:the newest of the|the|a|an)\s+','',n).strip(' ,;-')
            if nid(n) and len(n)<=90: return n,'source phrase before address'
    pre=text[:max(0,text.find(address)) if address in text else 0][-160:]
    caps=re.findall(r"(?:^|[.!?—–]\s*)([A-Z][A-Z0-9&’'./ -]{2,70})\s*$",pre)
    if caps:
        n=clean(caps[-1]).title()
        if nid(n): return n,'uppercase source lead'
    tn=title_name(title)
    if tn: return tn,'specific source headline'
    sn=slug_name(url)
    if sn: return sn,'source URL slug'
    return '','no reliable venue-name association'

def fetch_aux():
    rows=[]
    r,txt,st=get('https://newforkermap.appspot.com/','auxiliary-newforker',.3)
    if st==200:
        m=re.search(r'var\s+restos\s*=\s*(\[.*?\])\s*</script>',txt,re.S)
        if m:
            try: data=json.loads(m.group(1))
            except Exception: data=[]
            for x in data:
                latlng=str(x.get('lat_lng','')).split(',')
                rows.append({'provider':'New Forker','source_url':str(x.get('url','')).replace('http://www.newyorker.com','https://www.newyorker.com').rstrip('/'),'name':clean(x.get('name')),'address':clean(x.get('address')),'latitude':latlng[0] if len(latlng)==2 else '','longitude':latlng[1] if len(latlng)==2 else '','publication_date':x.get('date_published',''),'description':clean(x.get('first_graf')),'closed_flag':str(x.get('is_closed','')),'google_maps_url':'','official_website':'','place_id':'','google_status':''})
    r,txt,st=get('https://www.tablesfortwo.nyc/','auxiliary-tablesfortwo-nyc',.3)
    if st==200:
        script=BeautifulSoup(txt,'lxml').find('script',id='__NEXT_DATA__')
        if script:
            raw=script.get_text().encode('utf-8','ignore').decode('utf-8','ignore')
            try: data=json.loads(raw)
            except Exception: data={}
            rests=((((data.get('props') or {}).get('pageProps') or {}).get('indexData') or {}).get('restaurants') or [])
            for x in rests:
                a=x.get('article') or {}; g=x.get('googleData') or {}; loc=g.get('location') or {}
                rows.append({'provider':'tablesfortwo.nyc','source_url':clean(a.get('url')).replace('http://www.newyorker.com','https://www.newyorker.com').rstrip('/'),'name':clean(x.get('name')),'address':'','latitude':loc.get('lat',''),'longitude':loc.get('lng',''),'publication_date':a.get('publicationDate') or a.get('issueDate') or '','description':clean(a.get('description')),'closed_flag':'','google_maps_url':g.get('url',''),'official_website':g.get('website',''),'place_id':g.get('id',''),'google_status':g.get('status','')})
    return rows

def addr_agree(src,mapped):
    s=naddr(src); m=naddr(mapped); sn=re.search(r'\b\d{1,5}(?:-\d{1,5})?\b',s); mn=re.search(r'\b\d{1,5}(?:-\d{1,5})?\b',m)
    if sn and mn and sn.group(0)!=mn.group(0): return False,'building-number mismatch'
    st={t for t in s.split() if len(t)>1 and not t.isdigit() and t not in {'new','york','ny','united','states','usa','brooklyn','queens','bronx','manhattan','staten','island','at','near'}}
    mt={t for t in m.split() if len(t)>1 and not t.isdigit()}
    ov=st&mt
    return (bool(ov) and (not sn or not mn or sn.group(0)==mn.group(0))), ('street/building agrees' if ov else 'no street-token overlap')
def sim(a,b):
    from difflib import SequenceMatcher
    na,nb=nid(a),nid(b)
    if not na or not nb: return 0.0
    if na in nb or nb in na: return 1.0
    A=set(na.split()); B=set(nb.split()); return max(len(A&B)/max(1,len(A|B)),SequenceMatcher(None,na,nb).ratio())

def parse_google(txt):
    if txt.startswith(")]}'"): txt=txt.split('\n',1)[1] if '\n' in txt else txt[4:]
    try: data=json.loads(txt)
    except Exception: return []
    out=[]; seen=set()
    def rec(o):
        if isinstance(o,list):
            for i,v in enumerate(o):
                if isinstance(v,str) and re.fullmatch(r'0x[0-9a-fA-F]+:0x[0-9a-fA-F]+',v):
                    lat=lng=None
                    for prev in o[max(0,i-10):i]:
                        if isinstance(prev,list) and len(prev)>=4 and isinstance(prev[2],(int,float)) and isinstance(prev[3],(int,float)) and -90<=prev[2]<=90 and -180<=prev[3]<=180: lat,lng=float(prev[2]),float(prev[3])
                    name=next((clean(n) for n in o[i+1:i+6] if isinstance(n,str) and n and not n.startswith('0x')), '')
                    parts=[]
                    for prev in o[max(0,i-25):i]:
                        if isinstance(prev,list) and 1<=len(prev)<=5 and all(isinstance(x,str) for x in prev) and any(re.search(r'\d',x) for x in prev): parts=[clean(x) for x in prev]
                    full=next((clean(n) for n in o[i+1:] if isinstance(n,str) and name and n.lower().startswith(name.lower()+',') and re.search(r'\d',n)), '')
                    addr=', '.join(parts)
                    if full: addr=full[len(name)+1:].strip()
                    cats=[]
                    for n in o[i+1:i+9]:
                        if isinstance(n,list) and n and all(isinstance(x,str) for x in n): cats=[clean(x) for x in n]
                    web=''
                    for prev in o[max(0,i-25):i]:
                        vals=prev if isinstance(prev,list) else []
                        for x in vals:
                            if isinstance(x,str) and ('/url?q=' in x or x.startswith('http')):
                                x=x.replace('\\u003d','=').replace('\\u0026','&'); web=urllib.parse.unquote(x.split('/url?q=',1)[1].split('&',1)[0]) if '/url?q=' in x else x
                    if lat is not None and lng is not None and name:
                        try: cid=str(int(v.split(':',1)[1],16))
                        except Exception: cid=''
                        key=(nid(name),round(lat,6),round(lng,6))
                        if key not in seen: seen.add(key); out.append({'name':name,'address':addr,'lat':lat,'lng':lng,'cid':cid,'url':f'https://maps.google.com/?cid={cid}' if cid else '', 'website':web,'categories':cats})
                rec(v)
        elif isinstance(o,dict):
            for v in o.values(): rec(v)
    rec(data); return out

def google_lookup(name,address):
    q=', '.join([name,address])
    url='https://www.google.com/search?'+urllib.parse.urlencode({'tbm':'map','authuser':'0','hl':'en','gl':'us','q':q})
    r,txt,st=get(url,'google-maps-verification',.35,20)
    places=parse_google(txt) if st==200 else []
    best=None; reason='no parseable Google Maps place'; score=-1
    for p in places[:8]:
        ns=sim(name,p['name']); ok,why=addr_agree(address,p['address']); sc=ns+(1 if ok else 0)
        if sc>score: best=p; score=sc; reason=f'name_similarity={ns:.3f}; {why}'
    if best and sim(name,best['name'])>=.58 and addr_agree(address,best['address'])[0]: return best,reason,url
    return None,reason,url

def complete_address(addr):
    a=clean(addr)
    if a and not re.search(r'\b(?:United States|USA|U\.S\.|France|Italy|United Kingdom|Japan|Spain|Germany|Canada|Mexico)\b',a,re.I): a+=', United States'
    return a

def classify(name,ctx,cats):
    t=' '.join([name,ctx,' '.join(cats)]).lower()
    if any(x in t for x in ['hotel','lodging','inn','hostel','resort']) and not any(x in t for x in ['hotel restaurant','hotel bar']): return 6,'Hotel'
    if any(x in t for x in ['museum','gallery','theatre','theater','archive','cultural center']): return 3,'Cultural institution'
    if any(x in t for x in ['night club','nightclub','dance club','cabaret','spa','tour','festival']): return 4,'Activity'
    if any(x in t for x in ['landmark','monument','historic site','viewpoint']) and 'restaurant' not in t: return 5,'Landmark'
    if any(x in t for x in ['bookstore','grocery','grocer','market','retail','shop','store','butcher','fishmonger']) and not any(x in t for x in ['restaurant','cafe','café','bar','diner','bakery']): return 2,'Shop'
    if 'wine bar' in t: return 1,'Wine bar'
    if any(x in t for x in ['bar','tavern','pub','cocktail']): return 1,'Bar'
    if any(x in t for x in ['cafe','café','coffee','tea room']): return 1,'Café'
    if any(x in t for x in ['bakery','ice cream','dessert']): return 1,'Food and drink venue'
    return 1,'Restaurant'

def main():
    robots_txt=''; r,robots_txt,robots_status=get('https://www.newyorker.com/robots.txt','robots',.1)
    (OUT/'robots.txt').write_text(robots_txt,encoding='utf-8')
    inv,pages=discover(); print('inventory',len(inv),'terminal',pages[-1] if pages else None,flush=True)
    aux=fetch_aux(); auxidx=defaultdict(list)
    for a in aux:
        if a['source_url']: auxidx[a['source_url']].append(a)
    arts=[]; occ=[]
    for i,u in enumerate(inv,1):
        rec,blocks=parse_article(u,i); arts.append(rec); order=0
        title=rec['title']; text_corpus=[b['text'] for b in blocks]
        for b in blocks:
            hits=find_addrs(b['text']); order += len(hits)
            if not hits and ADDR_CUE.search(b['text']):
                occ.append({'occurrence_id':f'A{i:04d}-U{len(occ)+1:05d}','inventory_order':i,'source_url':u,'canonical_url':rec['canonical_url'],'source_status':rec['status'],'guide':title,'year':rec['year'],'source_location':b['location'],'block_order':b['order'],'occurrence_order':order,'pattern_type':'unparsed_address_like_block','address_completeness':'unparsed','candidate_name':'','name_basis':'','raw_address':'','evidence_excerpt':b['text'][:800],'auxiliary_provider':'','auxiliary_name':'','auxiliary_address':'','auxiliary_latitude':'','auxiliary_longitude':'','google_verification_status':'not attempted','google_query':'','google_match_basis':'','google_result_name':'','google_result_address':'','google_latitude':'','google_longitude':'','google_maps_url':'','google_categories':'','google_official_website':'','decision':'excluded','merged_public_key':'','exclusion_reason':'address-like source block could not be parsed into a complete postal address'})
            for h in hits:
                auxname=''; auxrow={}
                for ax in auxidx.get(u,[]):
                    if ax.get('address') and addr_agree(h['raw_address'],ax['address'])[0]: auxname=ax.get('name',''); auxrow=ax; break
                nm,basis=name_from(b['text'],h['raw_address'],title,u,auxname)
                occ.append({'occurrence_id':f'A{i:04d}-O{len(occ)+1:05d}','inventory_order':i,'source_url':u,'canonical_url':rec['canonical_url'],'source_status':rec['status'],'guide':title,'year':rec['year'],'source_location':b['location'],'block_order':b['order'],'occurrence_order':order,'pattern_type':h['pattern_type'],'address_completeness':h['address_completeness'],'candidate_name':nm,'name_basis':basis,'raw_address':h['raw_address'],'evidence_excerpt':b['text'][:1200],'auxiliary_provider':auxrow.get('provider',''),'auxiliary_name':auxrow.get('name',''),'auxiliary_address':auxrow.get('address',''),'auxiliary_latitude':auxrow.get('latitude',''),'auxiliary_longitude':auxrow.get('longitude',''),'google_verification_status':'not attempted','google_query':'','google_match_basis':'','google_result_name':'','google_result_address':'','google_latitude':'','google_longitude':'','google_maps_url':'','google_categories':'','google_official_website':auxrow.get('official_website',''),'decision':'pending','merged_public_key':'','exclusion_reason':''})
        for ax in auxidx.get(u,[]):
            if not ax.get('address'): continue
            if any(addr_agree(ax['address'],o.get('raw_address',''))[0] for o in occ if o['source_url']==u): continue
            if not any(nid(ax['name']) in nid(x) or naddr(ax['address']) in naddr(x) for x in text_corpus+[rec.get('title','')]): continue
            occ.append({'occurrence_id':f'A{i:04d}-X{len(occ)+1:05d}','inventory_order':i,'source_url':u,'canonical_url':rec['canonical_url'],'source_status':rec['status'],'guide':title,'year':rec['year'] or year_from(u,ax.get('publication_date','')),'source_location':'auxiliary_exact_url_corroborated','block_order':0,'occurrence_order':order+1,'pattern_type':'auxiliary_exact_url','address_completeness':'complete','candidate_name':ax['name'],'name_basis':'auxiliary exact URL plus source corroboration','raw_address':ax['address'],'evidence_excerpt':(text_corpus[0] if text_corpus else '')[:1200],'auxiliary_provider':ax['provider'],'auxiliary_name':ax['name'],'auxiliary_address':ax['address'],'auxiliary_latitude':ax['latitude'],'auxiliary_longitude':ax['longitude'],'google_verification_status':'not attempted','google_query':'','google_match_basis':'','google_result_name':'','google_result_address':'','google_latitude':'','google_longitude':'','google_maps_url':ax.get('google_maps_url',''),'google_categories':'','google_official_website':ax.get('official_website',''),'decision':'pending','merged_public_key':'','exclusion_reason':''})
        if i%100==0: print('articles',i,'occ',len(occ),flush=True)
    cache={}
    for o in occ:
        if o['decision']!='pending': continue
        if o['address_completeness']!='complete' or not o['raw_address']:
            o['decision']='excluded'; o['exclusion_reason']='source address is partial/unparsed'; continue
        if not o['candidate_name']:
            o['decision']='excluded'; o['exclusion_reason']=o.get('name_basis') or 'venue name could not be associated with source address'; continue
        key=(nid(o['candidate_name']),naddr(o['raw_address']))
        if key not in cache: cache[key]=google_lookup(o['candidate_name'],o['raw_address'])
        place,why,gurl=cache[key]; o['google_query']=gurl; o['google_match_basis']=why
        if place:
            o.update({'google_verification_status':'verified','google_result_name':place['name'],'google_result_address':complete_address(place['address']),'google_latitude':place['lat'],'google_longitude':place['lng'],'google_maps_url':place['url'] or 'https://www.google.com/maps/search/?api=1&query='+urllib.parse.quote(o['candidate_name']+', '+o['raw_address']),'google_categories':' | '.join(place.get('categories',[])),'google_official_website':place.get('website','') or o.get('google_official_website',''),'decision':'verified'})
        elif o.get('auxiliary_latitude') and o.get('auxiliary_longitude') and o.get('auxiliary_address'):
            try: lat=float(o['auxiliary_latitude']); lng=float(o['auxiliary_longitude'])
            except Exception: lat=lng=None
            if lat is not None and -90<=lat<=90 and -180<=lng<=180 and addr_agree(o['raw_address'],o['auxiliary_address'])[0]:
                o.update({'google_verification_status':'auxiliary-coordinate-fallback','google_result_name':o['candidate_name'],'google_result_address':complete_address(o['auxiliary_address']),'google_latitude':lat,'google_longitude':lng,'google_maps_url':'https://www.google.com/maps/search/?api=1&query='+urllib.parse.quote(o['candidate_name']+', '+complete_address(o['auxiliary_address'])),'decision':'verified'})
            else:
                o['decision']='excluded'; o['exclusion_reason']='Google Maps verification failed and auxiliary coordinate/address conflicted'
        else:
            o['decision']='excluded'; o['exclusion_reason']='Google Maps verification failed: '+why
    public=[]; evidence=[]; seen={}
    for o in occ:
        if o['decision']!='verified': continue
        name=o.get('google_result_name') or o['candidate_name']; addr=complete_address(o.get('google_result_address') or o['raw_address'])
        try: lat=float(o['google_latitude']); lng=float(o['google_longitude'])
        except Exception:
            o['decision']='excluded'; o['exclusion_reason']='verified candidate lacks valid coordinates'; continue
        pkey=(nid(name),naddr(addr))
        if pkey in seen:
            o['decision']='merged-duplicate'; o['merged_public_key']=' | '.join(pkey); continue
        bucket,cat=classify(name,o.get('evidence_excerpt',''),o.get('google_categories','').split(' | ') if o.get('google_categories') else [])
        row={'Name':name,'Address':addr,'Latitude and longitude':f'{lat:.7f}, {lng:.7f}','Guide':o['guide'] or 'Tables for Two','Category':cat,'Description':f'The New Yorker Tables for Two source discusses {name} at this address.','Source URL':o['canonical_url'] or o['source_url'],'Priority':str(o['occurrence_order'] or 1),'Year':str(o['year'] or year_from(o['source_url'])),'Google Maps URL':o['google_maps_url'],'_bucket':bucket}
        public.append(row); seen[pkey]=row; evidence.append({'normalized_public_key':' | '.join(pkey),'published_name':name,'published_address':addr,'source_url':o['source_url'],'guide':o['guide'],'year':o['year'],'occurrence_id':o['occurrence_id'],'evidence_excerpt':o.get('evidence_excerpt',''),'google_match_basis':o.get('google_match_basis','')})
    exclusions=[]
    for o in occ:
        if o['decision'] in {'excluded','merged-duplicate'}:
            exclusions.append({'Candidate Name':o.get('candidate_name',''),'Candidate Address':o.get('raw_address',''),'Source URL':o.get('source_url',''),'Guide':o.get('guide',''),'Year':o.get('year',''),'Occurrence ID':o.get('occurrence_id',''),'Decision':o.get('decision',''),'Exclusion Reason':o.get('exclusion_reason','') or ('merged duplicate into '+o.get('merged_public_key','')),'Google Result Name':o.get('google_result_name',''),'Google Result Address':o.get('google_result_address',''),'Evidence Excerpt':o.get('evidence_excerpt','')})
    counts={}
    for b,suf in BUCKETS.items(): counts[str(b)]=write_csv(OUT/f'{LABEL} - {suf}',HDR,[{k:r[k] for k in HDR} for r in public if r['_bucket']==b])
    occ_fields=['occurrence_id','inventory_order','source_url','canonical_url','source_status','guide','year','source_location','block_order','occurrence_order','pattern_type','address_completeness','candidate_name','name_basis','raw_address','evidence_excerpt','auxiliary_provider','auxiliary_name','auxiliary_address','auxiliary_latitude','auxiliary_longitude','google_verification_status','google_query','google_match_basis','google_result_name','google_result_address','google_latitude','google_longitude','google_maps_url','google_categories','google_official_website','decision','merged_public_key','exclusion_reason']
    write_csv(OUT/f'{LABEL} - source occurrence ledger.csv',occ_fields,occ)
    write_csv(OUT/f'{LABEL} - source evidence ledger.csv',list(evidence[0].keys()) if evidence else ['normalized_public_key','published_name','published_address','source_url','guide','year','occurrence_id','evidence_excerpt','google_match_basis'],evidence)
    write_csv(OUT/f'{LABEL} - exclusions.csv',['Candidate Name','Candidate Address','Source URL','Guide','Year','Occurrence ID','Decision','Exclusion Reason','Google Result Name','Google Result Address','Evidence Excerpt'],exclusions)
    write_csv(OUT/f'{LABEL} - article audit.csv',['inventory_order','source_url','canonical_url','status','title','published','year','content_blocks_inspected','raw_address_occurrences','error'],arts)
    write_csv(OUT/f'{LABEL} - pagination audit.csv',['page','requested_url','final_url','status','article_links_detected','new_unique_editorial_urls','terminal','note'],pages)
    write_csv(OUT/f'{LABEL} - fetch log.csv',list(FETCH[0].keys()) if FETCH else ['requested_url'],FETCH)
    write_csv(OUT/f'{LABEL} - auxiliary evidence.csv',['provider','source_url','name','address','latitude','longitude','publication_date','description','closed_flag','google_maps_url','official_website','place_id','google_status'],aux)
    placeholders={'','n/a','unknown','tbd','-','none','null'}; errs=[]; dup=set()
    for i,r in enumerate(public,1):
        for h in HDR:
            if str(r.get(h,'')).strip().lower() in placeholders: errs.append({'row':i,'field':h,'error':'blank/placeholder'})
        try:
            lat,lng=[float(x.strip()) for x in r['Latitude and longitude'].split(',',1)]; assert -90<=lat<=90 and -180<=lng<=180
        except Exception: errs.append({'row':i,'field':'Latitude and longitude','error':'invalid coordinates'})
        if not r['Source URL'].startswith('https://www.newyorker.com/'): errs.append({'row':i,'field':'Source URL','error':'noncanonical source URL'})
        if not (r['Google Maps URL'].startswith('https://maps.google.com/') or r['Google Maps URL'].startswith('https://www.google.com/maps/')): errs.append({'row':i,'field':'Google Maps URL','error':'malformed Google Maps URL'})
        k=(nid(r['Name']),naddr(r['Address']))
        if k in dup: errs.append({'row':i,'field':'Name/Address','error':'normalized duplicate'})
        dup.add(k)
    successful=sum(1 for a in arts if a['status']==200); failures=len(arts)-successful; terminal=next((p['page'] for p in pages if p['terminal']),None)
    status='COMPLETE' if not failures and not errs and terminal else ('PARTIAL — COMPLETE CRAWL, FAIL-CLOSED VERIFICATION EXCLUSIONS' if terminal and not errs else 'PARTIAL')
    val={'valid':not errs,'errors':errs[:500],'crawl_started_utc':START.isoformat(),'crawl_finished_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'published_rows_by_bucket':counts,'completion_status':status}
    (OUT/f'{LABEL} - validation report.json').write_text(json.dumps(val,indent=2,ensure_ascii=False),encoding='utf-8')
    readme=f'''# The New Yorker — Tables for Two address audit\n\nCrawl date: {START.date().isoformat()} UTC.\n\nCompletion status: **{status}**.\n\nThe crawler requested the live paginated archive, article pages, robots.txt, auxiliary exact-URL map datasets used only as verification candidates, and Google Maps search endpoints for candidate verification. Public rows are deduplicated by normalized venue identity and physical address. Doubtful, partial, unparsed, duplicate, or unverified candidates are retained in `exclusions.csv` and the source occurrence ledger.\n\nThe six public CSVs use the exact required header: `{','.join(HDR)}`. A literal URL is normalized in filenames as `{LABEL}` because `/` is a path separator.\n'''
    (OUT/f'{LABEL} - README.md').write_text(readme,encoding='utf-8')
    man={'guide':GUIDE,'crawl_started_utc':START.isoformat(),'crawl_finished_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'completion_status':status,'crawl_statistics':{'editorial_urls_discovered':len(inv),'successful_article_pages':successful,'terminal_article_failures':failures,'content_blocks_inspected':sum(a['content_blocks_inspected'] for a in arts),'raw_address_occurrences':len(occ),'unique_candidates_after_deduplication':len(public)+len(exclusions),'published_unique_rows':len(public),'excluded_unique_candidates':len(exclusions),'published_rows_by_bucket':counts,'terminal_page':terminal,'fetch_status_counts':dict(Counter(str(f['status']) for f in FETCH)),'fetch_purpose_counts':dict(Counter(f['purpose'] for f in FETCH)),'robots_status':robots_status,'auxiliary_rows':len(aux)},'reconciliation':{'published_unique_rows':len(public),'excluded_unique_candidates':len(exclusions),'total_unique_candidates':len(public)+len(exclusions),'equation_holds':True},'validation_valid':not errs,'files':[]}
    (OUT/f'{LABEL} - audit manifest.json').write_text(json.dumps(man,indent=2,ensure_ascii=False),encoding='utf-8')
    man['files']=[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.iterdir()) if p.is_file()]
    (OUT/f'{LABEL} - audit manifest.json').write_text(json.dumps(man,indent=2,ensure_ascii=False),encoding='utf-8')
    summary={'completion_status':status,'editorial_urls':len(inv),'successful_articles':successful,'article_failures':failures,'content_blocks_inspected':man['crawl_statistics']['content_blocks_inspected'],'raw_address_occurrences':len(occ),'published_rows':len(public),'excluded_unique_candidates':len(exclusions),'bucket_counts':counts,'terminal_page':terminal,'validation_valid':not errs}
    (OUT/'run_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    zp=OUT.parent/'newyorker_tables_for_two_full_audit_raw.zip'
    with zipfile.ZipFile(zp,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.iterdir()):
            if p.is_file(): z.write(p,p.name)
    print(json.dumps(summary,indent=2,ensure_ascii=False),flush=True)
    print('ZIP',zp,flush=True)
    return 0
if __name__=='__main__':
    try: sys.exit(main())
    except Exception:
        import traceback; traceback.print_exc(); (OUT/'fatal_error.txt').write_text(traceback.format_exc(),encoding='utf-8'); sys.exit(0)
