import sys
import argparse
from pathlib import Path

# 确保在 Windows 控制台输出 UTF-8，防止中文乱码
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from engine import TiandaoEngine
from characters_preset import PRESET_CHARACTERS

def main():
    parser = argparse.ArgumentParser(description="【天道】多智能体凡人流修仙小说自动演化系统")
    parser.add_argument(
        "--rounds",
        type=int,
        default=None,
        help="演化总轮次 (默认读取配置，通常建议 4~6 轮)"
    )
    parser.add_argument(
        "--chars",
        type=str,
        default="han_li,nangong_xuan,gu_chang_qing,su_mei_er",
        help="参战角色ID列表，以英文逗号分隔（可选: han_li, nangong_xuan, gu_chang_qing, su_mei_er）"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="模拟测试模式（不消耗真实 API，快速验证多智能体运转逻辑）"
    )

    args = parser.parse_args()
    char_list = [c.strip() for c in args.chars.split(",") if c.strip()]

    print("""
    =======================================================
       🌌 【天 道】—— 多智能体凡人流修仙小说演化系统
    =======================================================
    * 角色 Agent：心怀鬼胎、双盲博弈、内心算计与表面言行彻底分离
    * 天道 Agent：把控主线大势、客观战力判定、大劫因果注入
    * 史官 Agent：推演日志自动淬炼为凡人流网文原味章节
    =======================================================
    """)

    if args.mock:
        print(">> 已启用【模拟演练模式】，演示双盲博弈与天道裁决流程...")
        from mock_engine import run_mock_demo
        run_mock_demo(char_list, rounds=args.rounds or 3)
        return

    try:
        engine = TiandaoEngine(char_keys=char_list)
        if args.rounds:
            engine.world.max_rounds = args.rounds
        
        engine.run_all()
    except ValueError as ve:
        print(f"\n[配置提示] {ve}")
        print("请打开 `c:\\Work\\天道\\.env`，填写你的大模型 API KEY 后重新运行：")
        print("    python main.py")
        print("\n或者先体验模拟演示：")
        print("    python main.py --mock")
    except Exception as e:
        print(f"\n[运行异常] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
