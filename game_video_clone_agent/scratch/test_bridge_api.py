# -*- coding: utf-8 -*-
"""
Test script for DesktopApiBridge in start_app.py
"""
import os
import sys
import json
from pathlib import Path

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Import helper and bridge
try:
    from start_app import DesktopApiBridge, _is_drama_mode, GLOBAL_STATE
    print("Successfully imported start_app modules!")
except ImportError as e:
    print(f"Failed to import from start_app: {e}")
    sys.exit(1)

def run_tests():
    print("\n--- 🔍 TEST 1: _is_drama_mode helper ---")
    assert _is_drama_mode("RED") is True
    assert _is_drama_mode("BLUE") is True
    assert _is_drama_mode("ROLEPLAY") is True
    assert _is_drama_mode("CH_DRAMA") is True
    assert _is_drama_mode("DRAMA") is True
    assert _is_drama_mode("CH_SCIENCE") is False
    assert _is_drama_mode("CH_FOOD") is False
    assert _is_drama_mode("YELLOW") is False
    print("✅ _is_drama_mode assertions passed successfully!")

    bridge = DesktopApiBridge()

    print("\n--- 🧪 TEST 2: compile_story (Science Mode - CH_SCIENCE) ---")
    science_payload = {
        "mode_path": "CH_SCIENCE",
        "original_text": "在深邃的宇宙中，黑洞是引力的终极体现。光线一旦越过事件视界就再也无法逃逸。物理学家们通过引力波和周围吸积盘的辐射来间接观测它。",
        "pipeline_config": {
            "polish_flow": {"enabled": False},
            "voiceover_flow": {},
            "render_flow": {
                "style_presets": "High-quality 2D vector cartoon, physics formula background.",
                "seed": 40984180
            }
        }
    }
    
    res_science = bridge.compile_story(science_payload)
    print("Science Compile Response Status:", res_science.get("status"))
    if res_science.get("status") == "success":
        data = res_science.get("data", {})
        entities = data.get("extracted_entities", [])
        print("Extracted Entities (Science):", entities)
        # Should extract exactly 1 entity
        assert len(entities) == 1, f"Expected 1 entity, got {len(entities)}"
        print("✅ Science Compile Test Passed!")
    else:
        print("❌ Science Compile Failed:", res_science.get("detail"))
        sys.exit(1)

    print("\n--- 🎨 TEST 3: generate_assets (Science Mode - CH_SCIENCE) ---")
    gen_science_payload = {
        "entities": res_science["data"]["extracted_entities"],
        "global_style_prompt": "High-quality 2D vector cartoon, physics formula background.",
        "seed": 40984180
    }
    res_gen_science = bridge.generate_assets(gen_science_payload)
    print("Science Asset Gen Response Status:", res_gen_science.get("status"))
    if res_gen_science.get("status") == "success":
        assets = res_gen_science.get("assets", [])
        print("Generated Science Assets:", assets)
        # Should generate exactly 1 asset
        assert len(assets) == 1, f"Expected 1 asset card, got {len(assets)}"
        assert assets[0]["svgType"] == "scene"
        
        # Verify full_story_v6.json contents
        full_story_path = BASE_DIR / "data" / "runs" / GLOBAL_STATE["current_run_id"] / "scripts" / "full_story_v6.json"
        assert full_story_path.exists(), "full_story_v6.json was not created!"
        story_data = json.loads(full_story_path.read_text(encoding="utf-8"))
        anchors = story_data["master_design"]["physical_char_anchors"]
        print("Science anchors written:", anchors)
        assert len(anchors) == 1, f"Expected 1 anchor, got {len(anchors)}"
        assert "supporting_scene" in anchors
        print("✅ Science Asset Generation Test Passed!")
    else:
        print("❌ Science Asset Generation Failed:", res_gen_science.get("detail"))
        sys.exit(1)

    print("\n--- 🔄 TEST 6: render_single_frame (Science Mode Redraw - cast_01) ---")
    # Redraw the science card (cast_01). It should resolve as "scene" instead of "character".
    redraw_science_payload = {
        "target_id": "cast_01",
        "prompt": "Flat 2D vector sci-tech infographic illustration, no characters, clean",
        "seed": 40984180
    }
    res_redraw_science = bridge.render_single_frame(redraw_science_payload)
    print("Science Redraw Response Status:", res_redraw_science.get("status"))
    if res_redraw_science.get("status") == "success":
        svg_type = res_redraw_science.get("svgType")
        print("Science Redraw Card Type (svgType):", svg_type)
        # ASSERT: In science mode, cast_01 must resolve to "scene" background card!
        assert svg_type == "scene", f"Expected 'scene', got {svg_type!r}"
        print("✅ Science Redraw Card Type Assertion Passed!")
    else:
        print("❌ Science Redraw Failed:", res_redraw_science.get("detail"))
        sys.exit(1)

    print("\n--- 🎭 TEST 4: compile_story (Drama Mode - RED) ---")
    drama_payload = {
        "mode_path": "RED",
        "original_text": "老钟表匠坐在布满灰尘的机械工坊里，用颤抖的手指擦拭着一枚古老的逆动怀表。这枚怀表指针正逆向旋转，仿佛在倒流时间。",
        "pipeline_config": {
            "polish_flow": {"enabled": False},
            "voiceover_flow": {},
            "render_flow": {
                "style_presets": "Cyanide-and-Happiness, comic book style, vibrant flat colors.",
                "seed": 40984180
            }
        }
    }

    res_drama = bridge.compile_story(drama_payload)
    print("Drama Compile Response Status:", res_drama.get("status"))
    if res_drama.get("status") == "success":
        data = res_drama.get("data", {})
        entities = data.get("extracted_entities", [])
        print("Extracted Entities (Drama):", entities)
        # Should extract exactly 3 entities
        assert len(entities) == 3, f"Expected 3 entities, got {len(entities)}"
        print("✅ Drama Compile Test Passed!")
    else:
        print("❌ Drama Compile Failed:", res_drama.get("detail"))
        sys.exit(1)

    print("\n--- 🎨 TEST 5: generate_assets (Drama Mode - RED) ---")
    gen_drama_payload = {
        "entities": res_drama["data"]["extracted_entities"],
        "global_style_prompt": "Cyanide-and-Happiness, comic book style, vibrant flat colors.",
        "seed": 40984180
    }
    res_gen_drama = bridge.generate_assets(gen_drama_payload)
    print("Drama Asset Gen Response Status:", res_gen_drama.get("status"))
    if res_gen_drama.get("status") == "success":
        assets = res_gen_drama.get("assets", [])
        print("Generated Drama Assets count:", len(assets))
        # Should generate exactly 3 assets
        assert len(assets) == 3, f"Expected 3 asset cards, got {len(assets)}"
        
        # Verify full_story_v6.json contents
        full_story_path = BASE_DIR / "data" / "runs" / GLOBAL_STATE["current_run_id"] / "scripts" / "full_story_v6.json"
        assert full_story_path.exists(), "full_story_v6.json was not created for Drama!"
        story_data = json.loads(full_story_path.read_text(encoding="utf-8"))
        anchors = story_data["master_design"]["physical_char_anchors"]
        print("Drama anchors written:", anchors)
        assert len(anchors) == 3, f"Expected 3 anchors, got {len(anchors)}"
        assert "middle" in anchors
        assert "supporting_scene" in anchors
        assert "supporting_prop" in anchors
        print("✅ Drama Asset Generation Test Passed!")
    else:
        print("❌ Drama Asset Generation Failed:", res_gen_drama.get("detail"))
        sys.exit(1)

    print("\n--- 🔄 TEST 7: render_single_frame (Drama Mode Redraw - cast_01) ---")
    # Redraw the drama card (cast_01). It should resolve as "character".
    redraw_drama_payload = {
        "target_id": "cast_01",
        "prompt": "A cute stickman representation of old watchmaker, white background",
        "seed": 40984180
    }
    res_redraw_drama = bridge.render_single_frame(redraw_drama_payload)
    print("Drama Redraw Response Status:", res_redraw_drama.get("status"))
    if res_redraw_drama.get("status") == "success":
        svg_type = res_redraw_drama.get("svgType")
        print("Drama Redraw Card Type (svgType):", svg_type)
        # ASSERT: In drama mode, cast_01 must resolve to "character" protagonist card!
        assert svg_type == "character", f"Expected 'character', got {svg_type!r}"
        print("✅ Drama Redraw Card Type Assertion Passed!")
    else:
        print("❌ Drama Redraw Failed:", res_redraw_drama.get("detail"))
        sys.exit(1)

    print("\n--- 💾 TEST 8: Channel presets double-track persistence (save_channels & get_channels) ---")
    # Back up the original file if it exists
    channels_file = BASE_DIR / "data" / "channels_presets.json"
    backup_existed = False
    original_content = ""
    if channels_file.exists():
        backup_existed = True
        original_content = channels_file.read_text(encoding="utf-8")

    try:
        test_channels = [
            {
                "id": "ch_science",
                "name": "硬核科普",
                "channelType": "science",
                "presets": {
                    "image": "Custom Sci-Tech Style",
                    "storyboard": "Custom Infographic Rules"
                }
            }
        ]
        
        # Save channels
        save_res = bridge.save_channels(test_channels)
        assert save_res.get("status") == "success", "Failed to save channels presets"
        assert channels_file.exists(), "channels_presets.json was not created!"
        
        # Get channels
        get_res = bridge.get_channels()
        assert get_res.get("status") == "success", "Failed to get channels presets"
        loaded = get_res.get("channels", [])
        print("Loaded channels from file:", loaded)
        
        # Verify content
        assert len(loaded) == 1
        assert loaded[0]["id"] == "ch_science"
        assert loaded[0]["presets"]["image"] == "Custom Sci-Tech Style"
        assert loaded[0]["presets"]["storyboard"] == "Custom Infographic Rules"
        print("✅ Channel Presets double-track persistence assertions passed successfully!")
    finally:
        # Restore the original file
        if backup_existed:
            channels_file.write_text(original_content, encoding="utf-8")
        elif channels_file.exists():
            channels_file.unlink()

    print("\n🎉 ALL TESTS COMPLETED AND PASSED PERFECTLY!")

if __name__ == "__main__":
    run_tests()
