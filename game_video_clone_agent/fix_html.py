# -*- coding: utf-8 -*-
import sys

with open('palette_studio.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

fixed = 0
for i, line in enumerate(lines):
    # Find the problematic outline line in ch_science (line ~1067)
    if 'outline:' in line and '\u73b0\u8c61\u2192\u539f\u7406' in line and 'ch_science' not in line:
        # This is the line with unescaped quotes: 按"现象→原理→..."
        # Find: the raw " chars around 现象...结论
        # Replace them with Chinese brackets
        original = line
        
        # Find the pattern: a literal " before 现象 and after 结论
        # The line contains: ...按"现象→原理→实验证据→颠覆性结论"逻辑链...
        line = line.replace('\u6309\"\u73b0\u8c61\u2192\u539f\u7406\u2192\u5b9e\u9a8c\u8bc1\u636e\u2192\u98a0\u8986\u6027\u7ed3\u8bba\"', 
                           '\u6309\u300c\u73b0\u8c61\u2192\u539f\u7406\u2192\u5b9e\u9a8c\u8bc1\u636e\u2192\u98a0\u8986\u6027\u7ed3\u8bba\u300d')
        
        if line != original:
            lines[i] = line
            fixed += 1
            print(f'Fixed line {i+1}')
        else:
            print(f'Pattern not found on line {i+1}, checking content:')
            # Print chars around 现象
            idx = line.find('\u73b0\u8c61')
            if idx > 0:
                print(f'  Chars before 现象: {repr(line[max(0,idx-3):idx+20])}')

print(f'Total fixed: {fixed}')

with open('palette_studio.html', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Saved.')
