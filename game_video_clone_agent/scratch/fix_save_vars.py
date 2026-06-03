import re
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

target_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "palette_studio.html")

with open(target_path, "r", encoding="utf-8") as f:
    content = f.read()

# Normalize line endings
content = content.replace("\r\n", "\n")

# -----------------------------------------------------------------
# FIX 1: The truncated voiceover/polish/storyboard/cast variable declarations
# We need to find the partial line and inject the full block.
# -----------------------------------------------------------------

# Find lines around the truncation
OLD_VARS = '      const voiceover = document.getElementById("chEditorVoiceover").v\n<truncated 552 bytes>\n !== -1) {'

NEW_VARS = '''      const voiceover = document.getElementById("chEditorVoiceover").value.trim();
      const polish = document.getElementById("chEditorPolish").value.trim();
      const storyboard = document.getElementById("chEditorStoryboard").value.trim();
      const cast = document.getElementById("chEditorCast").value.trim();
      const hasCustomPresets = outline || image || voiceover || polish || storyboard || cast;
      const channelType = document.querySelector('input[name="chChannelType"]:checked')?.value || "science";

      const idx = state.channels.findIndex(c => c.id === _editingChannelId);
      if (idx !== -1) {'''

if OLD_VARS in content:
    content = content.replace(OLD_VARS, NEW_VARS)
    print("FIX 1: Replaced truncated variable block - SUCCESS")
else:
    print("FIX 1: Could not find exact match, trying regex...")
    # Try with regex to handle slight variations
    pattern = r'      const voiceover = document\.getElementById\("chEditorVoiceover"\)\.v\n<truncated \d+ bytes>\n !== -1\) \{'
    match = re.search(pattern, content)
    if match:
        content = content[:match.start()] + NEW_VARS + content[match.end():]
        print("FIX 1: Replaced via regex - SUCCESS")
    else:
        print("FIX 1: FAILED - could not find truncated block")
        # Print surrounding context for debugging
        search_str = 'const voiceover = document.getElementById("chEditorVoiceover").v'
        idx2 = content.find(search_str)
        if idx2 >= 0:
            print(f"Found partial at char {idx2}:")
            print(repr(content[idx2:idx2+200]))

# -----------------------------------------------------------------
# FIX 2: Also fix the getChannelPresets to include cast (already done via multi_replace)
# Verify it's there
# -----------------------------------------------------------------
if "cast:       channel.presets.cast" in content:
    print("FIX 2: getChannelPresets cast key - already present OK")
else:
    print("FIX 2: getChannelPresets cast key - MISSING, injecting...")
    OLD_PRESETS_FN = '''        storyboard: channel.presets.storyboard || DEFAULT_PRESETS.storyboard
      };
    }'''
    NEW_PRESETS_FN = '''        storyboard: channel.presets.storyboard || DEFAULT_PRESETS.storyboard,
        cast:       channel.presets.cast       || DEFAULT_PRESETS.cast
      };
    }'''
    if OLD_PRESETS_FN in content:
        content = content.replace(OLD_PRESETS_FN, NEW_PRESETS_FN)
        print("FIX 2: getChannelPresets cast key - INJECTED")
    else:
        print("FIX 2: Could not inject - string not found")

# -----------------------------------------------------------------
# Write output
# -----------------------------------------------------------------
with open(target_path, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\nDone. File written: {len(content)} chars")

# Verify cast appears in save function
idx3 = content.find('const cast = document.getElementById("chEditorCast")')
print(f"const cast = ... found at char: {idx3}")
