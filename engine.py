import json
import os
import time
from pathlib import Path
from typing import Dict, List, Any

from config import (
    API_KEY, BASE_URL, DEFAULT_MODEL, TIANDAO_MODEL,
    CHRONICLER_MODEL, MAX_ROUNDS, AUTO_GENERATE_NOVEL
)
from llm_client import LLMClient
from world_state import WorldState, RoundLog, CharacterAction
from characters_preset import PRESET_CHARACTERS
from agents.tiandao import TiandaoAgent
from agents.character import CharacterAgent
from agents.chronicler import ChroniclerAgent

class TiandaoEngine:
    """
    【天道自动演化引擎核心调度器】
    """

    def __init__(self, char_keys: List[str] = None):
        self.llm = LLMClient(api_key=API_KEY, base_url=BASE_URL)
        self.world = WorldState(max_rounds=MAX_ROUNDS)
        
        # 初始化天道与史官
        self.tiandao = TiandaoAgent(self.llm, TIANDAO_MODEL)
        self.chronicler = ChroniclerAgent(self.llm, CHRONICLER_MODEL)

        # 加载角色
        if not char_keys:
            char_keys = ["han_li", "nangong_xuan", "gu_chang_qing", "su_mei_er"]

        self.character_agents: Dict[str, CharacterAgent] = {}
        for k in char_keys:
            if k in PRESET_CHARACTERS:
                c_data = PRESET_CHARACTERS[k]
                self.world.characters[k] = c_data
                self.character_agents[k] = CharacterAgent(
                    char_id=k,
                    char_data=c_data,
                    llm_client=self.llm,
                    model_name=DEFAULT_MODEL
                )

        self.output_dir = Path(__file__).parent / "output"
        self.output_dir.mkdir(exist_ok=True)

    def print_banner(self, text: str):
        print("\n" + "=" * 65)
        print(f"  {text}")
        print("=" * 65)

    def run_round(self, round_num: int):
        self.print_banner(f"第 {round_num} 轮演化推演开始 (当前主线：{self.world.title})")

        # 1. 构建每个角色可感知的公开信息 (严格战争迷雾)
        public_chars = [
            {
                "name": c_data["name"],
                "title": c_data.get("title", ""),
                "public_profile": c_data["public_profile"]
            }
            for c_data in self.world.characters.values()
        ]

        latest_tiandao_event = ""
        public_history_summary = ""
        if self.world.history:
            last_round = self.world.history[-1]
            latest_tiandao_event = f"{last_round.environment_state}\n{last_round.tiandao_intervention or ''}"
            public_history_summary = f"前序战果：{last_round.arbitration_result[:200]}..."

        # 2. 角色在各自迷雾中决策
        round_actions: List[CharacterAction] = []
        for char_id, agent in self.character_agents.items():
            print(f"▶ [{agent.name}] 正在审时度势，密谋行止...")
            action = agent.act(
                round_num=round_num,
                scene_desc=self.world.scene_description,
                public_history_summary=public_history_summary,
                latest_tiandao_event=latest_tiandao_event,
                other_characters_public=public_chars
            )
            round_actions.append(action)

            # 终端高亮展示角色表里不一的博弈
            print(f"   【心机谋算(秘)】: {action.inner_thought}")
            print(f"   【言语辞令(明)】: \"{action.speech}\"")
            print(f"   【出手施法】: {action.action}\n")

        # 3. 天道进行因果律裁决
        print("☯ 【天道意志】降临，裁决众生因果与战局走向...")
        arbitration = self.tiandao.arbitrate(
            round_num=round_num,
            world=self.world,
            actions=round_actions
        )

        print(f"   【乾坤变异】: {arbitration.get('environment_change', '')}")
        if arbitration.get("fate_twist"):
            print(f"   【大劫/机缘】: {arbitration.get('fate_twist')}")
        print(f"   【因果裁决】: {arbitration.get('arbitration_summary', '')}\n")

        # 4. 记录历史
        log = RoundLog(
            round_number=round_num,
            environment_state=arbitration.get("environment_change", ""),
            tiandao_intervention=arbitration.get("fate_twist", ""),
            actions=round_actions,
            arbitration_result=arbitration.get("arbitration_summary", "")
        )
        self.world.history.append(log)

    def run_all(self):
        start_time = time.time()
        self.print_banner("天道智能体演化引擎启动：凡人流多角色推演")
        print(f"参战阵营角色: {', '.join([c['name'] for c in self.world.characters.values()])}")
        print(f"总推演轮次: {self.world.max_rounds}")

        for r in range(1, self.world.max_rounds + 1):
            self.run_round(r)
            time.sleep(1)

        # 保存原始推演日志
        raw_log_path = self.output_dir / "evolution_log.json"
        raw_data = [
            {
                "round": r.round_number,
                "environment": r.environment_state,
                "tiandao_intervention": r.tiandao_intervention,
                "arbitration": r.arbitration_result,
                "actions": [
                    {
                        "name": a.char_name,
                        "inner_thought": a.inner_thought,
                        "speech": a.speech,
                        "action": a.action
                    }
                    for a in r.actions
                ]
            }
            for r in self.world.history
        ]
        with open(raw_log_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2)
        print(f"\n✔ 演化推演日志已保存至: {raw_log_path}")

        # 史官著书生成小说章节
        if AUTO_GENERATE_NOVEL:
            self.print_banner("【史官入席】正在将 Agent 推演历史熔铸为凡人流长篇小说正文...")
            novel_content = self.chronicler.write_chapter(self.world, self.world.history)
            
            novel_path = self.output_dir / "novel_chapter_01.md"
            with open(novel_path, "w", encoding="utf-8") as f:
                f.write(novel_content)
            
            print(f"\n✔ 小说正式章节撰写完成，已保存至: {novel_path}")
            print("\n" + "=" * 65)
            print("【小说正文预览】：\n")
            print(novel_content[:800] + "...\n(更多详见输出文件)")
            print("=" * 65)

        elapsed = time.time() - start_time
        print(f"\n✔ 全部演化与小说生成完毕，总耗时: {elapsed:.1f} 秒。")
