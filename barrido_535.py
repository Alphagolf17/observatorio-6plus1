"""Barrido reproducible: 3 días cerrados y rally previo. Sin señales con datos futuros."""
from __future__ import annotations
import io, json, time, datetime as dt
from pathlib import Path
import pandas as pd
import requests
import yfinance as yf

OUT=Path('output_535'); OUT.mkdir(exist_ok=True)
START='2026-07-01'
END=(dt.date.today()+dt.timedelta(days=1)).isoformat()
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 (compatible; research-data/1.0)'})

# Wikipedia maintains the live universe; this is NOT a point-in-time historical constituent list.
def sp500():
    url='https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    html=S.get(url,timeout=35);html.raise_for_status()
    tables=pd.read_html(io.StringIO(html.text))
    t=next(t for t in tables if 'Symbol' in t.columns and 'Security' in t.columns)
    return [(str(r.Symbol).replace('.','-'),str(r.Security),'SP500',str(r.get('GICS Sector',''))) for _,r in t.iterrows()]

# IBEX membership changes: check this list against the official composition for the chosen date.
IBEX=['ANA','ACX','ACS','AENA','AMS','MTS','SAB','SAN','BKT','BBVA','CABK','CLNX','COL','ENG','ELE','FER','FDR','GRF','IAG','IBE','ITX','IDR','LOG','MAP','MRL','NTGY','PUIG','RED','REP','ROVI','SCYR','SLR','TEF','UNI','VIS']
def ibex(): return [(x+'.MC',x,'IBEX35','') for x in IBEX]

def get_prices(ticker):
    # Small individual downloads, not a multi-hundred-megabyte archive.
    df=yf.download(ticker,start=START,end=END,auto_adjust=True,progress=False,threads=False,timeout=20)
    if df.empty:return None
    if isinstance(df.columns,pd.MultiIndex):df.columns=df.columns.get_level_values(0)
    df=df[['Close','Volume']].dropna(subset=['Close']).copy()
    df.index=pd.to_datetime(df.index).tz_localize(None).normalize()
    return df[~df.index.duplicated(keep='last')].sort_index()

def pct(a,b):return round(100*(a/b-1),3) if b and pd.notna(a) and pd.notna(b) else None

def calculate(ticker,name,market,sector,df):
    dates=['2026-10-26','2026-10-27','2026-10-28','2026-10-29','2026-10-30']
    vals={d:(float(df.loc[pd.Timestamp(d),'Close']) if pd.Timestamp(d) in df.index else None) for d in dates}
    r={'ticker':ticker,'nombre':name,'mercado':market,'sector':sector,'ultimo_dato':df.index[-1].strftime('%Y-%m-%d'),'sesiones_historicas':len(df)}
    for d in dates:r['cierre_'+d]=vals[d]
    for i,d in enumerate(dates[1:],1):r['variacion_'+d]=pct(vals[d],vals[dates[i-1]])
    r['variacion_27_29']=pct(vals['2026-10-29'],vals['2026-10-26'])
    r['variacion_27_30']=pct(vals['2026-10-30'],vals['2026-10-26'])
    # Rally from July to the highest close BEFORE the shock, and how much was retraced.
    prev=df.loc[(df.index>=pd.Timestamp(START))&(df.index<=pd.Timestamp('2026-10-26')),'Close']
    if len(prev)>=20:
        low=float(prev.min());high=float(prev.max());peak_date=prev.idxmax()
        r['max_previo']=round(high,5);r['fecha_max_previo']=peak_date.strftime('%Y-%m-%d')
        r['subida_desde_minimo_julio_pct']=pct(high,low)
        for day in ['2026-10-29','2026-10-30']:
            close=vals[day]
            r['retroceso_rally_'+day+'_pct']=round(100*(high-close)/(high-low),2) if close is not None and high>low else None
    r['volumen_20d_ratio']=round(float(df['Volume'].iloc[-1])/float(df['Volume'].iloc[-21:-1].mean()),3) if len(df)>21 and df['Volume'].iloc[-21:-1].mean()>0 else None
    r['datos_completos_27_29']=all(vals[d] is not None for d in dates[:4])
    return r

def main():
    errors=[];records=[];universe=[]
    for label,fn in [('SP500',sp500),('IBEX35',ibex)]:
        try: universe+=fn()
        except Exception as e:errors.append({'universo':label,'error':str(e)})
    # Intel is monitored even if it is not a member of the current S&P 500.
    if 'INTC' not in {x[0] for x in universe}:universe.append(('INTC','Intel (radar adicional)','EXTRA','Semiconductors'))
    for i,(ticker,name,market,sector) in enumerate(universe,1):
        try:
            df=get_prices(ticker)
            if df is None or len(df)<5:raise ValueError('Sin suficientes precios')
            records.append(calculate(ticker,name,market,sector,df))
        except Exception as e:errors.append({'ticker':ticker,'mercado':market,'error':str(e)})
        if i%50==0:print(f'Procesados {i}/{len(universe)}; correctos {len(records)}',flush=True)
        time.sleep(0.12)
    result=pd.DataFrame(records)
    if not result.empty:
        result.to_csv(OUT/'universo_completo.csv',index=False,encoding='utf-8-sig')
        for market in ['SP500','IBEX35','EXTRA']:
            x=result[result.mercado==market].copy()
            if len(x):
                x.sort_values('variacion_27_29').to_csv(OUT/f'{market}_ranking_27_29.csv',index=False,encoding='utf-8-sig')
                x.sort_values('retroceso_rally_2026-10-29_pct',ascending=False).to_csv(OUT/f'{market}_rallies_anulados.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(errors).to_csv(OUT/'errores_y_ausencias.csv',index=False,encoding='utf-8-sig')
    summary={'fecha_ejecucion_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'universo_detectado':len(universe),'series_descargadas':len(records),'errores':len(errors),'precios_completos_27_29':int(result.datos_completos_27_29.sum()) if not result.empty else 0,'nota':'Datos ajustados por splits/dividendos con yfinance; universo SP500 actual, no membresía histórica. Ibex lista preliminar: verificar composición oficial. 30 octubre incompleto hasta cierre.'}
    (OUT/'resumen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
