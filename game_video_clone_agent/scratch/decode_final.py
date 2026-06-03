import codecs
import os

for idx in [1960, 1968, 1980]:
    for typ in ['target', 'replacement']:
        path = f'scratch/step_{idx}_{typ}.txt'
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Strip whitespace and newlines first
            content = content.strip()
            
            # If the string starts and ends with double quotes, strip them
            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1]
                
            # Decode unicode escapes
            try:
                decoded = codecs.escape_decode(bytes(content, "utf-8"))[0].decode("utf-8")
            except Exception as e:
                print(f"Error decoding {path}: {e}")
                decoded = content
                
            with open(f'scratch/step_{idx}_{typ}_decoded.txt', 'w', encoding='utf-8') as f:
                f.write(decoded)
            print(f"Decoded {path} successfully!")
