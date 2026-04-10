import re
with open('/nextjs/.next/server/app/(dashboard)/mqtt/client-logs/page.js') as f:
    content = f.read()

matches = re.findall(r'\.logs|\.events|client_logs|clientLogs', content)
print('Fields found:', set(matches))

err = re.findall(r'Failed to fetch.{0,50}', content)
print('Error messages:', err[:5])

# Find context around events / logs
for pattern in [r'.events', r'.logs']:
    idx = content.find(pattern)
    if idx > -1:
        print(f'\nContext for {pattern}:')
        print(content[max(0,idx-100):idx+100])
