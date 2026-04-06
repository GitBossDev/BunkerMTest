import json
with open('/var/lib/mosquitto/dynamic-security.json') as f:
    ds = json.load(f)
for role in ds.get('roles', []):
    rname = role.get('rolename', '')
    if rname in ('admin', 'bunker', 'superuser'):
        print('Role:', rname)
        for acl in role.get('acls', []):
            print(' ', acl['acltype'], '|', acl['topic'], '| allow=', acl['allow'])
