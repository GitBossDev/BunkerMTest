import json

dynsec = '/var/lib/mosquitto/dynamic-security.json'
with open(dynsec) as f:
    d = json.load(f)

for r in d.get('roles', []):
    if r.get('rolename') == 'admin':
        # Remove any ACL entries with backslash or incorrect /# patterns
        r['acls'] = [a for a in r['acls']
                     if '\\' not in a.get('topic', '') and a.get('topic') != '/#']

        # Ensure publishClientSend for # (all user topics) exists
        has_send_hash = any(
            a['acltype'] == 'publishClientSend' and a['topic'] == '#' and a.get('allow')
            for a in r['acls']
        )
        if not has_send_hash:
            r['acls'].insert(0, {'acltype': 'publishClientSend', 'topic': '#', 'priority': 0, 'allow': True})

        print('Admin ACLs after fix:')
        for a in r['acls']:
            print(f"  {a['acltype']:35s} {a['topic']:40s} allow={a.get('allow')}")
        break

with open(dynsec, 'w') as f:
    json.dump(d, f, indent=2)
print('Saved.')
