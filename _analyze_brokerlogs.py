import re
with open('/nextjs/.next/server/app/(dashboard)/mqtt/broker-logs/page.js') as f:
    content = f.read()

# Find error messages and how logs are used
errors = re.findall(r'Failed to [^"]{0,60}', content)
print('Error messages:', errors[:10])

# Find .logs usage
idx = content.find('.logs')
while idx != -1 and idx < len(content):
    print('\n.logs context:')
    print(content[max(0,idx-100):idx+150])
    idx = content.find('.logs', idx+5)
    break  # just first occurrence
