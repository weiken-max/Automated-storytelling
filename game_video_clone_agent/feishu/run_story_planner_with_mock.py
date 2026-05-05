import sys
import json
import importlib
from unittest.mock import patch
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

# 这个函数会劫持 V6 原有的大纲生成机制，直接返回我们在飞书上审批过的大纲！
def read_mocked_synopsis(topic):
    synopsis_path = BASE_DIR / "feishu" / "temp_synopsis.json"
    print(f"  [MOCK] 成功拦截 generate_synopsis！正在注入您审批过的大纲: {synopsis_path}")
    with open(synopsis_path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_mocked():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", type=str, required=True)
    parser.add_argument("--regen_stage", type=str, default=None)
    parser.add_argument("--duration", type=float, default=1.25)
    args, unknown = parser.parse_known_args()

    # 先导入模块对象，再 patch.object，避免字符串 patch 在某些环境下解析失败
    planner = importlib.import_module("src.story_planner_v6")
    with patch.object(planner, "generate_synopsis", side_effect=read_mocked_synopsis):
        # 把伪装的命令行参数传给主程序
        sys.argv = ["src/story_planner_v6.py", "--topic", args.topic]
        if args.regen_stage:
            sys.argv += ["--regen_stage", args.regen_stage]
        sys.argv += ["--duration", str(args.duration)]
        planner.main()

if __name__ == "__main__":
    run_mocked()
