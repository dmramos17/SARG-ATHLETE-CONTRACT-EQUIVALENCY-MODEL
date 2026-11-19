"""Featured deals from the latest three signing years in a saved snapshot."""
def recent_contracts(records,limit=6):
    valid=[r for r in records if isinstance(r.get('signing_year'),int) and r.get('value') and r['value']>0]
    end=max((r['signing_year'] for r in valid),default=None)
    start=end-2 if end is not None else None
    chosen=sorted((r for r in valid if r['signing_year']>=start),key=lambda r:(-r['value'],-r['signing_year'],r['id']))[:limit]
    return dict(ids=[r['id'] for r in chosen],start_year=start,end_year=end,
                definition='Largest reported deals from the latest three signing years available in this saved snapshot; not a live transaction feed.')
