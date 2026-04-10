#!/usr/bin/env python3
# Adds /api/logs/clients location to nginx config
conf_path = '/etc/nginx/conf.d/default.conf'

with open(conf_path) as f:
    content = f.read()

new_location = '''
    # Client Logs API - served by the clientlogs backend (port 1002)
    location /api/logs/clients {
        proxy_pass http://127.0.0.1:1002/api/v1/events;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # --- Next.js catch-all'''

old_marker = '\n    # --- Next.js catch-all'

if '# Client Logs API' in content:
    print('Client Logs location already present')
elif old_marker not in content:
    print('Marker not found')
else:
    content = content.replace(old_marker, new_location, 1)
    with open(conf_path, 'w') as f:
        f.write(content)
    print('Patched OK')
