#!/usr/bin/env python3
# Patches the nginx location for /api/logs/broker to inject the API key
conf_path = '/etc/nginx/conf.d/default.conf'
key_path = '/nextjs/data/.api_key'

with open(key_path) as f:
    api_key = f.read().strip()

with open(conf_path) as f:
    content = f.read()

old = '        proxy_set_header X-API-Key $http_x_api_key;\n    }\n\n    # --- Next.js catch-all'
new = '        proxy_set_header X-API-Key "' + api_key + '";\n    }\n\n    # --- Next.js catch-all'

if old not in content:
    print("Pattern not found, checking current content around logs/broker...")
    idx = content.find('/api/logs/broker')
    print(repr(content[idx-10:idx+200]))
else:
    content = content.replace(old, new)
    with open(conf_path, 'w') as f:
        f.write(content)
    print("Patched OK. API key: " + api_key[:8] + "...")
