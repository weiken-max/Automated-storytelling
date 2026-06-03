import sys
import os
import traceback

# Force redirect streams to log files
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

sys.stdout = open(os.path.join(base_dir, "pythonw_stdout.log"), "w", encoding="utf-8")
sys.stderr = open(os.path.join(base_dir, "pythonw_stderr.log"), "w", encoding="utf-8")

try:
    print("Starting start_app...")
    import start_app
    print("Imported successfully!")
    start_app.main()
except Exception as e:
    traceback.print_exc()
    sys.stderr.flush()
