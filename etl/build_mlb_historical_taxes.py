"""Generate auditable 2015–2024 tax inputs from archived source tables.

Run after downloading Tax Foundation's 2015–2024 state workbook. Annual state
compilations remain provisional; selected later changes use government sources.
"""
import argparse,csv,json,re,zipfile
import xml.etree.ElementTree as E
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[1]
STATE_SOURCE='https://taxfoundation.org/wp-content/uploads/2024/02/State-Individual-Income-Tax-Rates-and-Brackets-2015-2024_Tax_Foundation.xlsx'
LABELS=dict(zip(['Ala.','Alaska','Ariz.','Ark.','Calif.','Colo.','Conn.','Del.','D.C.','Fla.','Ga.','Hawaii','Idaho','Ill.','Ind.','Iowa','Kans.','Ky.','La.','Maine','Md.','Mass.','Mich.','Minn.','Miss.','Mo.','Mont.','Nebr.','Nev.','N.H.','N.J.','N.M.','N.Y.','N.C.','N.D.','Ohio','Okla.','Ore.','Pa.','R.I.','S.C.','S.D.','Tenn.','Tex.','Utah','Vt.','Va.','Wash.','W.Va.','Wis.','Wyo.'],['AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY']))
FEDERAL={
2015:([0,9225,37450,90750,189300,411500,413200],[0,18450,74900,151200,230450,411500,464850],6300,118500),
2016:([0,9275,37650,91150,190150,413350,415050],[0,18550,75300,151900,231450,413350,466950],6300,118500),
2017:([0,9325,37950,91900,191650,416700,418400],[0,18650,75900,153100,233350,416700,470700],6350,127200),
2018:([0,9525,38700,82500,157500,200000,500000],[0,19050,77400,165000,315000,400000,600000],12000,128400),
2019:([0,9700,39475,84200,160725,204100,510300],[0,19400,78950,168400,321450,408200,612350],12200,132900),
2020:([0,9875,40125,85525,163300,207350,518400],[0,19750,80250,171050,326600,414700,622050],12400,137700),
2021:([0,9950,40525,86375,164925,209425,523600],[0,19900,81050,172750,329850,418850,628300],12550,142800),
2022:([0,10275,41775,89075,170050,215950,539900],[0,20550,83550,178150,340100,431900,647850],12950,147000),
2023:([0,11000,44725,95375,182100,231250,578125],[0,22000,89450,190750,364200,462500,693750],13850,160200),
2024:([0,11600,47150,100525,191950,243725,609350],[0,23200,94300,201050,383900,487450,731200],14600,168600)}

def build(workbook,ca_file):
    z=zipfile.ZipFile(workbook);ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    strings=[''.join(s.itertext()) for s in E.fromstring(z.read('xl/sharedStrings.xml'))]
    brackets=defaultdict(list)
    for index,year in enumerate(range(2024,2014,-1),1):
        rows=[]
        for row in E.fromstring(z.read(f'xl/worksheets/sheet{index}.xml')).findall('x:sheetData/x:row',ns):
            values={}
            for c in row:
                v=c.find('x:v',ns)
                if v is not None:values[re.sub(r'\d','',c.attrib['r'])]=strings[int(v.text)] if c.attrib.get('t')=='s' else v.text
            rows.append(values)
        header=next(r for r in rows if r.get('A')=='State')
        rates=[k for k,v in header.items() if v=='Rates'];bounds=[k for k,v in header.items() if v=='Brackets']
        state=None
        for row in rows[2:]:
            label=re.sub(r'\s*\(.*','',row.get('A','')).strip()
            if label in LABELS:state=LABELS[label]
            if not state:continue
            for filing,rate_col,bound_col in zip(('single','mfj'),rates,bounds):
                try:rate=float(row[rate_col]);low=float(row[bound_col])
                except (KeyError,ValueError):continue
                if 0<rate<.2 and low>=0:brackets[year,state,filing].append((low,rate,STATE_SOURCE))
    # Government corrections to annual tables published before final rate changes.
    corrections={
      (2017,'IL'):(.043549,'https://tax.illinois.gov/content/dam/soi/en/web/tax/forms/incometax/documents/2017/individual/il-1040-instr.pdf'),
      (2023,'MI'):(.0405,'https://www.michigan.gov/taxes/questions/tax-faqs/income-tax-rate-change/income-tax-rate-change-overview'),
      (2024,'GA'):(.0539,'https://dor.georgia.gov/document/document/2024-it-511-individual-income-tax-booklet/download')}
    for y,r in {2019:.045,2020:.0455,2021:.045,2022:.044,2023:.044,2024:.0425}.items():corrections[y,'CO']=(r,'https://tax.colorado.gov/individual-income-tax-guide')
    for (year,state),(rate,source) in corrections.items():
        for filing in ('single','mfj'):brackets[year,state,filing]=[(0,rate,source)]
    az='https://azdor.gov/sites/default/files/2023-03/FORMS_INDIVIDUAL_2022_TablesXY.pdf'
    for filing,limit in [('single',28653),('mfj',57305)]:brackets[2022,'AZ',filing]=[(0,.0255,az),(limit,.0298,az)]
    for year,rates in {2019:[.0386,.0504,.0627,.0765],2020:[.0354,.0465,.0627,.0765],2021:[.0354,.0465,.053,.0765]}.items():
        for filing in ('single','mfj'):
            old=brackets[year,'WI',filing]
            if len(old)==4:brackets[year,'WI',filing]=[(low,rate,'https://www.revenue.wi.gov/Documents/DOR-Fall-2021-WI-Tax-Update-Handout.pdf') for (low,_,_),rate in zip(old,rates)]
    # Split CA mental-health and MA millionaires surtaxes from the base brackets.
    for key in list(brackets):
        year,state,filing=key
        if state=='CA':brackets[key]=[(low,rate,src) for low,rate,src in brackets[key] if rate<.13]
        if state=='MA':brackets[key]=[(low,rate,src) for low,rate,src in brackets[key] if rate<.09]
    if ca_file.exists():
        for year,row in json.loads(ca_file.read_text()).items():
            for filing in ('single','mfj'):
                pairs=row[filing]
                expected=[.01,.02,.04,.06,.08,.093,.103,.113,.123]
                if len(pairs)!=9 or any(abs(r-e)>1e-8 for (_,r),e in zip(pairs,expected)) or any(a[0]>=b[0] for a,b in zip(pairs,pairs[1:])):continue
                brackets[int(year),'CA',filing]=[(low,rate,row['source']) for low,rate in pairs]
    # Explicit 2021 values transcribed from the official schedule whose text wraps rows.
    source='https://www.ftb.ca.gov/forms/2021/2021-540-tax-rate-schedules.pdf'
    for filing,lows in [('single',[0,9325,22107,34892,48435,61214,312686,375221,625369]),('mfj',[0,18650,44214,69784,96870,122428,625372,750442,1250738])]:
        brackets[2021,'CA',filing]=[(low,rate,source) for low,rate in zip(lows,[.01,.02,.04,.06,.08,.093,.103,.113,.123])]
    output=ROOT/'data/processed/state_income_tax_brackets_2015_2024.csv'
    with output.open('w') as f:
        writer=csv.writer(f);writer.writerow(['tax_year','state_code','filing_status','bracket_order','lower_bound','rate','verification_status','source'])
        for (year,state,filing),rows in sorted(brackets.items()):
            rows=sorted(set(rows),key=lambda r:r[0])
            assert rows and len({r[0] for r in rows})==len(rows),(year,state,filing)
            for i,(low,rate,src) in enumerate(rows,1):writer.writerow([year,state,filing,i,low,rate,'provisional',src])
    params={}
    for year,(single,mfj,deduction,ss) in FEDERAL.items():
        params[str(year)]=dict(brackets=dict(single=single,mfj=mfj),rates=[.1,.15,.25,.28,.33,.35,.396] if year<2018 else [.1,.12,.22,.24,.32,.35,.37],standard_deduction=dict(single=deduction,mfj=2*deduction),ss_wage_base=ss,source=f'https://www.irs.gov/pub/irs-prior/i1040gi--{year}.pdf',payroll_source='https://www.ssa.gov/oact/cola/cbb.html')
    (ROOT/'data/curated/mlb_historical_federal.json').write_text(json.dumps(params,indent=2)+'\n')
    print('Generated',len(brackets),'state/filing/year schedules and',len(params),'federal years')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workbook',type=Path,default=ROOT/'data/raw/historical/state_tax_rates_2015_2024.xlsx');p.add_argument('--ca-file',type=Path,default=ROOT/'data/curated/mlb_historical_ca_brackets.json');a=p.parse_args();build(a.workbook,a.ca_file)
