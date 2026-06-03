import json
import os

with open(r'C:\Users\86198\.gemini\antigravity\brain\2407058c-fded-46a3-a898-61406a3aada8\.system_generated\logs\transcript.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        idx = data.get('step_index')
        if idx in [1960, 1968, 1980]:
            tool_calls = data.get('tool_calls', [])
            for call_idx, tc in enumerate(tool_calls):
                args = tc.get('args', {})
                target = args.get('TargetContent', '')
                replacement = args.get('ReplacementContent', '')
                
                # Write to scratch files
                os.makedirs('scratch', exist_ok=True)
                with open(f'scratch/step_{idx}_target.txt', 'w', encoding='utf-8') as tf:
                    tf.write(target)
                with open(f'scratch/step_{idx}_replacement.txt', 'w', encoding='utf-8') as rf:
                    rf.write(replacement)
                print(f"Extracted Step {idx} (Target size: {len(target)}, Replacement size: {len(replacement)})")
