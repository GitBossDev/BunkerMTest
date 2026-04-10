import re
with open('/nextjs/.next/server/app/(dashboard)/mqtt/client-logs/page.js') as f:
    content = f.read()

# Find getEvents definition
idx = content.find('getEvents')
if idx > -1:
    print('getEvents context:')
    print(content[max(0,idx-50):idx+200])

# Find getClientLogs context
idx2 = content.find('getClientLogs')
if idx2 > -1:
    print('\ngetClientLogs context:')
    print(content[max(0,idx2-50):idx2+200])
