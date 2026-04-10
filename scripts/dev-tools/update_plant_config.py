#!/usr/bin/env python3
"""Update plant_config.yaml: add plant/water-plant-1/ prefix + legacy sensors."""
import sys
import os

yaml_path = r'c:\Projects\BunkerMTest\BunkerMTest\water-plant-simulator\config\plant_config.yaml'

with open(yaml_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Normalize to LF for easier manipulation
content = content.replace('\r\n', '\n')

# ---- Sensor topic replacements ----
replacements = [
    ('topic: "sensors/tank1/level"',         'topic: "plant/water-plant-1/sensors/tank1/level"'),
    ('topic: "sensors/tank1/ph"',            'topic: "plant/water-plant-1/sensors/tank1/ph"'),
    ('topic: "sensors/tank1/turbidity"',     'topic: "plant/water-plant-1/sensors/tank1/turbidity"'),
    ('topic: "sensors/flow/inlet"',          'topic: "plant/water-plant-1/sensors/flow/inlet"'),
    ('topic: "sensors/flow/outlet"',         'topic: "plant/water-plant-1/sensors/flow/outlet"'),
    ('topic: "sensors/pump1/pressure"',      'topic: "plant/water-plant-1/sensors/pump1/pressure"'),
    ('topic: "sensors/pump2/pressure"',      'topic: "plant/water-plant-1/sensors/pump2/pressure"'),
    ('topic: "sensors/ambient/temperature"', 'topic: "plant/water-plant-1/sensors/ambient/temperature"'),
]

for old, new in replacements:
    if old in content:
        content = content.replace(old, new, 1)
        print(f'OK: {old[:40]}')
    else:
        print(f'SKIP (already done or not found): {old[:40]}')

# ---- Add legacy sensors after ambient_temperature block ----
legacy_block = '''
  # Legacy format sensors - publish non-JSON formats for compatibility testing
  flow_inlet_legacy:
    topic: "plant/water-plant-1/legacy/flow/inlet"
    unit: "L/min"
    min_value: 0
    max_value: 500
    initial_value: 100
    noise_stddev: 5.0
    format: "csv"

  flow_outlet_legacy:
    topic: "plant/water-plant-1/legacy/flow/outlet"
    unit: "L/min"
    min_value: 0
    max_value: 500
    initial_value: 100
    noise_stddev: 5.0
    format: "csv"

  ambient_temperature_legacy:
    topic: "plant/water-plant-1/legacy/ambient/temperature"
    unit: "\u00b0C"
    min_value: 15
    max_value: 35
    initial_value: 22
    noise_stddev: 1.0
    format: "plain"
'''

marker = '\n# Configuraci\u00f3n de actuadores'
if '# Legacy format sensors' in content:
    print('Legacy sensors block already present')
elif marker in content:
    content = content.replace(marker, legacy_block + marker, 1)
    print('OK: legacy sensors block added')
else:
    # Try English fallback
    marker2 = '\n# actuators'
    print(f'Marker not found. Looking for context...')
    idx = content.find('ambient_temperature:')
    print('Found ambient_temperature at:', idx)
    if idx > -1:
        # Find end of its block (next blank line + comment)
        end = content.find('\n\n#', idx)
        print('End of block at:', end, 'Content:', repr(content[end:end+50]))

with open(yaml_path, 'w', encoding='utf-8', newline='') as f:
    f.write(content)
print('File written.')
