from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class CharacterAction:
    char_id: str
    char_name: str
    inner_thought: str  # 私有内心独白（算计、杀心、推演，对外隐藏）
    speech: str         # 公开言语（伪装、试探、虚与委蛇）
    action: str         # 具体行动（施法、暗中扣动符箓、后撤选位）

@dataclass
class RoundLog:
    round_number: int
    environment_state: str                    # 天地异象与环境描写
    tiandao_intervention: Optional[str]        # 天道降下的突发劫数/机缘
    actions: List[CharacterAction]             # 各角色本轮行动
    arbitration_result: str                   # 天道因果判定结果（战损、中伏、局势演变）

@dataclass
class WorldState:
    title: str = "【大千修仙界 · 混沌初开】"
    scene_description: str = (
        "大千世界，混沌初定。天地玄黄，万物沉寂。"
        "四海八荒无钦定主角，无预设众生。"
        "运转天道即可引爆天地异象，因果律将自发引渡各方争渡修士入局演化。"
    )
    tiandao_master_plot: str = (
        "【天道至高法则 · 万类霜天竞自由】：\n"
        "天地不仁，以万物为刍狗。此间世界无任何天定主角，人人皆是自身命运之主宰！\n"
        "1. 绝无免死光环：无论何方修士，谁露出破绽或算计不周，谁就身死道消、沦为枯骨！\n"
        "2. 各怀长生执念：或求长生苟道，或求复仇证道，或求宗门霸业，或求魔道逍遥，人人皆为自己殊死博弈。\n"
        "3. 结局开放演化：宝物谁得、谁生谁死、谁逆风翻盘，全凭双方动作克制、底牌损耗与天道客观因果判定，绝不强行保送任何人！"
    )
    characters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    history: List[RoundLog] = field(default_factory=list)
    current_round: int = 0
    max_rounds: int = 5
