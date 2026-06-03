import json
import os

for idx in [1960, 1968, 1980]:
    # Read target and replacement
    for type_name in ['target', 'replacement']:
        file_path = f'scratch/step_{idx}_{type_name}.txt'
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Try parsing as JSON string if it's quoted
            try:
                # If it starts and ends with quotes, or has escaped quotes, parse it
                decoded = json.loads(content)
            except Exception:
                try:
                    # Fallback to eval or raw string parsing
                    decoded = json.loads('"' + content + '"')
                except Exception:
                    decoded = content
            
            with open(f'scratch/step_{idx}_{type_name}_decoded.txt', 'w', encoding='utf-8') as f:
                f.write(decoded)
            print(f"Decoded {file_path} to decoded.txt")
