"""Build supplemental signing arguments from the already audited input list."""
def supplemental_arguments(inputs):
    indices=[i for i,(role,_) in enumerate(inputs) if role=='release-supply-chain']
    if len(indices)!=1 or [role for role,_ in inputs[:2]]!=['profile-full','profile-release']:
        raise ValueError('Missing or ambiguous automatic/supplemental evidence boundary')
    rows=inputs[indices[0]:]
    if len({role for role,_ in rows})!=len(rows):raise ValueError('Duplicate supplemental evidence role')
    return [part for role,path in rows for part in ('--evidence',role+'='+str(path.resolve()))]
