import re
with open('/nextjs/.next/server/app/(dashboard)/mqtt/client-logs/page.js') as f:
    content = f.read()

# Find kK object definition which has getEvents
idx = content.find('kK')
print('kK context:')
print(content[max(0,idx-10):idx+500])
