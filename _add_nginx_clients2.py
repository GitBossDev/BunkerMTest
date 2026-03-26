#!/usr/bin/env python3
conf_path = '/etc/nginx/conf.d/default.conf'

with open(conf_path) as f:
    content = f.read()

old = '    # --- Next.js catch-all (handles all pages + /api/auth/*) ---\n    location / {'
new = '''    # Client Logs API - served by the clientlogs backend (port 1002)
    location /api/logs/clients {
        proxy_pass http://127.0.0.1:1002/api/v1/events;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # --- Next.js catch-all (handles all pages + /api/auth/*) ---
    location / {'''

if old not in content:
    print('Marker not found!')
    print('Looking for:', repr(old[:80]))
else:
    content = content.replace(old, new, 1)
    with open(conf_path, 'w') as f:
        f.write(content)
    print('Patched OK')
