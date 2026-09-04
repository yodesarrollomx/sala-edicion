#!/usr/bin/env python3
"""Arma manual.html: mete las capturas como data URI en la plantilla."""
import json, re, sys
b64 = json.load(open('img/_b64.json'))
html = open('plantilla.html').read()
faltan = []
for m in set(re.findall(r'\{\{IMG:([\w-]+)\}\}', html)):
    if m not in b64: faltan.append(m)
    html = html.replace('{{IMG:%s}}' % m, b64.get(m, ''))
open('manual.html','w').write(html)
print('manual.html', len(html)//1024, 'KB', '· faltan:', faltan or 'ninguna')
