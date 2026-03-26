with open('/etc/nginx/conf.d/default.conf') as f:
    lines = f.readlines()

new_lines = []
skip = False
inserted = False
for line in lines:
    if '# Broker Logs - config backend port 1005' in line:
        skip = True
        if not inserted:
            new_lines.append('    # Broker Logs - config backend port 1005\n')
            new_lines.append('    location /api/logs/broker {\n')
            new_lines.append('        proxy_pass http://127.0.0.1:1005/api/v1/broker;\n')
            new_lines.append('        proxy_set_header Host $host;\n')
            new_lines.append('        proxy_set_header X-API-Key $http_x_api_key;\n')
            new_lines.append('    }\n')
            new_lines.append('\n')
            inserted = True
        continue
    if skip and '# --- Next.js catch-all' in line:
        skip = False
    if skip:
        continue
    new_lines.append(line)

with open('/etc/nginx/conf.d/default.conf', 'w') as f:
    f.writelines(new_lines)
print('Done, lines:', len(new_lines))
