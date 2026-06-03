import sys
import os
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from start_app import DesktopApiBridge

def main():
    print("Running DesktopApiBridge Regression Test...")
    bridge = DesktopApiBridge()

    # 1. Test health check
    res = bridge.health_check()
    print("Health check response:", res)
    assert res["status"] == "success", f"Health check failed: {res}"

    # 2. Test get_channels
    res = bridge.get_channels()
    print("get_channels response status:", res["status"])
    assert res["status"] == "success", f"get_channels failed: {res}"

    # 3. Test save_channels
    dummy_channels = [
        {
            "id": "ch_drama",
            "channelType": "drama",
            "name": "剧情故事",
            "emoji": "🎭",
            "color": "#EF4444",
            "locked": True,
            "presets": None
        }
    ]
    
    # Backup existing channels presets if exists
    channels_file = os.path.join(BASE_DIR, "data", "channels_presets.json")
    backup_file = os.path.join(BASE_DIR, "data", "channels_presets.json.bak")
    backup_created = False
    if os.path.exists(channels_file):
        shutil.copy(channels_file, backup_file)
        backup_created = True

    try:
        res = bridge.save_channels(dummy_channels)
        print("save_channels response status:", res["status"])
        assert res["status"] == "success", f"save_channels failed: {res}"

        res_check = bridge.get_channels()
        print("Re-fetched channels count:", len(res_check["channels"]))
        assert len(res_check["channels"]) == 1, "Save/get channels mismatch"
        assert res_check["channels"][0]["id"] == "ch_drama", "Channel ID mismatch"
        print("Save/load channels tests passed successfully!")
    finally:
        # Restore backup if created
        if backup_created:
            shutil.copy(backup_file, channels_file)
            os.remove(backup_file)
            print("Restored original channels_presets.json backup.")
        elif os.path.exists(channels_file):
            os.remove(channels_file)

    print("All DesktopApiBridge tests passed successfully!")

if __name__ == "__main__":
    main()
