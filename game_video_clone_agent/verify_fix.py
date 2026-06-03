# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('palette_studio.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print('Line 1067:', repr(lines[1066][:200]))
print()
print('Checking lines 1048-1070 for unescaped quotes:')
for i in range(1047, 1070):
    line = lines[i]
    if 'outline' in line:
        # Count the raw double-quote positions
        print(f'L{i+1} (outline): length={len(line)}')
        print(f'  First 150 chars: {repr(line[:150])}')
