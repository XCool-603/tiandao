import json
from typing import List, Dict, Any
from llm_client import LLMClient
from world_state import CharacterAction, WorldState

import json
from typing import List, Dict, Any
from llm_client import LLMClient
from world_state import CharacterAction, WorldState

class TiandaoAgent:
    """
    【天道 Agent (The Heaven's Will / Master Arbiter)】
    客观掌控全题材世界因果大势与自然法则，依据角色真实行动与物理因果进行双盲推演裁决，
    杜绝钦定主角与剧情杀，让命运与局势自然涌现。
    """

    def __init__(self, llm_client: LLMClient, model_name: str):
        self.llm = llm_client
        self.model = model_name

    def arbitrate(
        self,
        round_num: int,
        world: WorldState,
        actions: List[CharacterAction]
    ) -> Dict[str, Any]:
        """
        天道进行本轮因果推演与客观裁决：
        1. 判定各角色的攻击、防御、暗算、逃跑是否成功，依据各自真实动机、实力与站位客观推演。
        2. 结合世界环境物理法则与相克机制，结算伤势、道具损耗与战果。
        3. 降下符合大势的外部变数或环境突变（打破僵局，自然催化冲突）。
        """
        actions_context = ""
        char_names = []
        for act in actions:
            char_names.append(act.char_name)
            actions_context += (
                f"【{act.char_name}】\n"
                f"  - 真实心机/算计 (私密): {act.inner_thought}\n"
                f"  - 表面所言 (公开): \"{act.speech}\"\n"
                f"  - 具体动作/施法: {act.action}\n\n"
            )

        genre_name = getattr(world, "genre", "") or "通用幻想"
        world_title = getattr(world, "title", "当前世界")

        prompt = f"""
你是不容忤逆的【{genre_name}因果律天道意志 / 至高推演主宰】。
你客观掌控大千因果命数、物质生克与该世界的自然法则。

【核心推演原则】：
1. **无钦定免死主角，人人皆是自身命运的主角，人人皆凭手段争渡！**
2. 严禁模板化、套路化或刻板剧情杀。胜负生死完全取决于角色的智计谋略、底牌道具、站位破绽与环境因果。
3. 若算计有失同样会中伏重创；若布局精妙同样能反杀得逞。没有无脑降智，没有主角光环，客观推演万物因果走向。

【当前世界环境】：
{world.scene_description}

【世界主线暗线与大势法则】：
{world.tiandao_master_plot}

【本轮为第 {round_num} / {world.max_rounds} 轮交锋】

【各角色本轮提报之行动】：
{actions_context}

作为至高天道，你必须拥有冷酷绝对、不偏不倚的法官视角，执行以下职责：
1. 【客观因果判定】：
   - 裁决各角色动作的真实成效：严格依据双方实力悬殊、道具/武器克制、地形站位与心理博弈。
   - 给出本轮交锋的客观事实判定，详细交代双方招式碰擦的实况。
2. 【大势演化 / 外部变数注入】：
   - 若场面陷入僵局或言语试探过多，天道以环境异变、外力冲击、第三方势力干预等自然规律打破平衡，逼迫角色亮出真实面目与深层底牌。
3. 【局势演进与生死状态结算】：
   - 根据真实交锋成败判定角色生死走向（alive: 在场活跃 / dead: 阵亡陨落 / escaped: 负伤或见机脱离战场）。
4. 【大千世界自然引渡（动态生成新角色）】：
   - 冲突声响、异宝动静或能量震荡，会自然吸引世界中的其他争渡者被动或主动卷入！
   - 若当前在场存活角色少于 5 人，天道可依据当前【{genre_name}】题材与现场因果，**自主生成 1 位符合世界观的新角色**（如路过豪强、巡视密探、敌对阵营援兵、潜伏伺机者等），直接投放下场！

请严格按以下 JSON 格式返回，切勿输出多余废话：
```json
{{
  "environment_change": "本轮交锋过后的环境剧变与现场动荡描写 (60~120字)",
  "fate_twist": "天道推演降下的外部突发变数或危机催化 (40~80字)",
  "arbitration_summary": "客观因果裁决结论（各人动作碰撞实效、伤势变化、底牌消耗） (80~150字)",
  "character_fates": {{
    "角色名A": "alive",
    "角色名B": "dead",
    "角色名C": "escaped"
  }},
  "new_arrival": {{
    "should_spawn": false,
    "name": "新角色姓名 (2~3字)",
    "title": "头衔/尊号/身份",
    "camp": "所属阵营/流派",
    "cultivation_level": "符合该世界观的境界或战力阶位",
    "public_profile": "外貌与展现出的气场装备描写 (60~100字)",
    "secret_profile": "【真实隐秘底牌与暗中心机准则】 (80~120字)",
    "inventory": ["携带道具/武器/底牌1", "道具2"],
    "entrance_reason": "因何被卷入战局的合理因果缘由"
  }}
}}
```
"""

        messages = [
            {"role": "system", "content": f"你是冷酷客观掌控【{genre_name}】大千因果的至高天道推演者。严禁刻板定义，让冲突与命运客观自然涌现。"},
            {"role": "user", "content": prompt}
        ]

        raw_res = self.llm.chat(self.model, messages, temperature=0.6)
        parsed = self.llm.extract_json(raw_res)

        if not parsed:
            acting_names = "、".join(char_names) if char_names else "当场各方"
            parsed = {
                "environment_change": f"现场气流剧烈震荡，交锋余波扩散，{world_title}的局势陡然紧绷。",
                "fate_twist": "暗处潜藏的危机被交锋引动，一股强烈的危险气息骤然笼罩战场！",
                "arbitration_summary": f"{acting_names}各自施展手段正面对撼，招式碰擦间互有攻防试探，胜负悬于一线。",
                "character_fates": {name: "alive" for name in char_names},
                "is_climax": False
            }

        return parsed
