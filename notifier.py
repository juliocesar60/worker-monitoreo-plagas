def split_lines(text: str, max_chars: int):
    words = (text or "").split()
    line, out = [], []
    for w in words:
        if sum(len(x) for x in line) + len(line) + len(w) > max_chars:
            out.append(" ".join(line)); line = [w]
        else:
            line.append(w)
    if line: out.append(" ".join(line))
    return out

def build_recommendation(severity: str) -> str:
    s = (severity or '').lower()
    if 'crit' in s or 'sev' in s:
        return ('Aplicar control químico/biorracional de inmediato. '
                'Monitoreo cada 12 h y retiro de hojas muy afectadas.')
    if 'lev' in s or 'mod' in s:
        return ('Monitoreo 24–48 h. Control biológico y trampas. '
                'Optimizar riego y manejo del cultivo.')
    return ('Monitoreo preventivo cada 72 h y buenas prácticas fitosanitarias.')
