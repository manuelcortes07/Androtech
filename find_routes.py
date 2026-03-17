#!/usr/bin/env python3
import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

routes = re.findall(r'@app\.route\([\'"](.*?)[\'"]', content)
print('Rutas encontradas en app.py:')
for route in routes:
    print(f'  {route}')

print(f'\nTotal de rutas: {len(routes)}')