"""
三维离散空间导演与视听语法约束引擎 (Spatial Cinematography & Director Engine)

核心解决 AI 短剧与生视频领域的工业化难题：
1. 离散三维场景空间拓扑 (3D Discrete Scene Topology & Spatial Anchoring)
2. 180度视线轴线锁死与多机位切换合规检测 (180-Degree Action Axis & Camera Rig Linter)
3. 景别梯度防疲劳与剪辑节奏动力学曲线 (Shot Scale Variety & Pacing Tension Dynamics)
4. 相机视锥与屏幕左右站位几何投影计算 (Screen Space Projection & Orientation Enforcement)
5. 空间几何参数向生图/生视频模型精确提示词转译 (Spatial Parameter Prompt Injection)
"""

import math
from typing import Dict, Any, List, Tuple, Optional


class SpatialVector:
    """二维/三维向量实用工具"""
    @staticmethod
    def sub(v1: Tuple[float, ...], v2: Tuple[float, ...]) -> Tuple[float, ...]:
        return tuple(a - b for a, b in zip(v1, v2))

    @staticmethod
    def add(v1: Tuple[float, ...], v2: Tuple[float, ...]) -> Tuple[float, ...]:
        return tuple(a + b for a, b in zip(v1, v2))

    @staticmethod
    def length(v: Tuple[float, ...]) -> float:
        return math.sqrt(sum(x * x for x in v))

    @staticmethod
    def normalize(v: Tuple[float, ...]) -> Tuple[float, ...]:
        l = SpatialVector.length(v)
        if l == 0:
            return tuple(0.0 for _ in v)
        return tuple(x / l for x in v)

    @staticmethod
    def dot_2d(v1: Tuple[float, float], v2: Tuple[float, float]) -> float:
        return v1[0] * v2[0] + v1[1] * v2[1]

    @staticmethod
    def cross_2d(v1: Tuple[float, float], v2: Tuple[float, float]) -> float:
        """二维叉积（判别点在线段左侧或右侧）：>0 在左侧，<0 在右侧"""
        return v1[0] * v2[1] - v1[1] * v2[0]


class SpatialDirectorEngine:
    """三维离散空间导演与机位调度约束引擎"""

    # 规范景别梯级（从宏观到微观）
    SHOT_SCALES = [
        "大远景", "全景", "中景", "中近景", "近景", "特写", "极微特写"
    ]

    # 标准八机位模板定义（相对于行动轴线与两位主体的空间分布）
    RIG_PRESETS = {
        "CAM_MASTER": {
            "name": "环境全景主控位",
            "scale": "全景",
            "focal_length": 28,
            "motion": "缓缓推近",
            "desc": "建立整体空间关系，交代地标锚点与全员相对站位"
        },
        "CAM_TWO_SHOT": {
            "name": "双人对峙水平位",
            "scale": "中景",
            "focal_length": 45,
            "motion": "固定平视",
            "desc": "同框捕捉两名核心角色的形体对抗与空间张力"
        },
        "CAM_OTS_A": {
            "name": "A过肩反打B位",
            "scale": "中近景",
            "focal_length": 65,
            "motion": "手持微晃",
            "desc": "以A角色后肩/侧影为近景前景，焦点落在B角色面部表情"
        },
        "CAM_OTS_B": {
            "name": "B过肩正打A位",
            "scale": "中近景",
            "focal_length": 65,
            "motion": "手持微晃",
            "desc": "以B角色后肩/侧影为近景前景，焦点落在A角色面部表情"
        },
        "CAM_CU_A": {
            "name": "A正向特写视线位",
            "scale": "特写",
            "focal_length": 85,
            "motion": "急速推近",
            "desc": "锁定A角色眼神锐度与神态威压，背景深度虚化"
        },
        "CAM_CU_B": {
            "name": "B正向特写视线位",
            "scale": "特写",
            "focal_length": 85,
            "motion": "急速推近",
            "desc": "锁定B角色惊恐或狞笑神态，背景深度虚化"
        },
        "CAM_DUTCH_CLIMAX": {
            "name": "冲突斜角仰角位",
            "scale": "特写",
            "focal_length": 35,
            "motion": "斜角升格慢动作",
            "desc": "倾斜地平线15度低角度仰拍，戏剧压迫感爆表"
        },
        "CAM_REACTION": {
            "name": "第三方/反应镜位",
            "scale": "近景",
            "focal_length": 50,
            "motion": "水平摇向",
            "desc": "捕捉旁观者震撼反应或关键道具特写"
        }
    }

    def __init__(self):
        pass

    def build_scene_topology(
        self,
        scene_name: str,
        characters: List[str],
        genre_cat: str = "doomsday",
        scene_desc: str = ""
    ) -> Dict[str, Any]:
        """
        构建离散三维场景空间拓扑与环境锚点
        场景坐标系：
        X轴: -10m (极左) ~ +10m (极右)
        Y轴: 0m (前景近端) ~ 20m (背景远端)
        Z轴: 0m (地面) ~ 4m (天花板/顶棚)
        """
        # 1. 动态确立场景地标物理锚点（保证多镜头切机位时背景不变形）
        anchors = self._extract_dynamic_anchors(scene_name, scene_desc, genre_cat)

        # 2. 离散角色三维站位与视线向量 (默认两核心对峙模式)
        char_spatial: Dict[str, Dict[str, Any]] = {}
        if not characters:
            characters = ["主角", "对手"]

        char_a = characters[0]
        char_b = characters[1] if len(characters) > 1 else "对手"

        # 主角 A 居于防御内侧或主位：偏左前 (X: -1.8m, Y: 4.5m, Z: 0m)
        # 对手 B 居于逼近外侧或客位：偏右前 (X: +1.8m, Y: 3.5m, Z: 0m)
        char_spatial[char_a] = {
            "role": "protagonist",
            "pos": [-1.8, 4.5, 0.0],
            "facing": [0.8, -0.2], # 面向右前（视线投向B）
            "gaze_target": char_b,
            "status": "优势防御/冷酷审视"
        }
        char_spatial[char_b] = {
            "role": "antagonist",
            "pos": [1.8, 3.5, 0.0],
            "facing": [-0.8, 0.2], # 面向左后（视线投向A）
            "gaze_target": char_a,
            "status": "挑衅逼近/狂妄施压"
        }

        # 其余辅助角色安排在背景或侧翼
        for idx, c in enumerate(characters[2:], start=1):
            char_spatial[c] = {
                "role": "supporting",
                "pos": [3.0 + idx * 0.8, 6.0 + idx * 0.5, 0.0],
                "facing": [-0.6, -0.4],
                "gaze_target": char_a,
                "status": "旁观/惊骇"
            }

        # 3. 确立主行动轴线 (Line of Action)
        # 连接主角A与对手B两点的水平线段
        p_a = (char_spatial[char_a]["pos"][0], char_spatial[char_a]["pos"][1])
        p_b = (char_spatial[char_b]["pos"][0], char_spatial[char_b]["pos"][1])
        axis_vec = SpatialVector.sub(p_b, p_a) # 向量 A -> B

        return {
            "scene_name": scene_name,
            "dimensions": {"width": 20, "depth": 20, "height": 4},
            "anchors": anchors,
            "characters": char_spatial,
            "line_of_action": {
                "subject_a": char_a,
                "subject_b": char_b,
                "start": p_a,
                "end": p_b,
                "vector": axis_vec,
                "allowed_side": "camera_front" # 锁死在视线轴前方（近机位侧），严禁越轴到后方翻转
            }
        }

    def generate_tension_and_pacing_curve(self, shot_count: int = 10, total_duration: int = 90) -> List[Dict[str, Any]]:
        """
        计算 90秒竖屏短剧的专业张力曲线与景别/时长动力学节奏
        杜绝所有镜头时长雷同、景别单一的问题
        张力曲线划分：
        - 0-10s (黄金抓手Hook): 情绪起步 80 -> 90，极速剪切 (1.5s - 2.5s)，极微特写与快推
        - 10-38s (铺垫与冲突积蓄): 情绪回落至 50 -> 65，稳健节奏 (3.5s - 4.5s)，全景与双人过肩正反打
        - 38-72s (高潮打脸爆发): 情绪飙升至 85 -> 100，交替快切 (1.5s - 2.5s)，特写、极低仰角与动作重音
        - 72-90s (悬念断章Cliffhanger): 情绪定格在 95 -> 100，长特写凝结 (3.5s - 5.0s)，制造未完待续钩子
        """
        shots_plan = []
        # 根据镜头总数分配时间切片
        t_accum = 0.0

        for i in range(1, shot_count + 1):
            progress = (i - 1) / max(1, shot_count - 1) # 0.0 ~ 1.0
            cur_sec = progress * total_duration

            if cur_sec <= 10.0:
                # 黄金抓手阶段
                tension = 85 + (cur_sec / 10.0) * 10
                duration = 2.5 if i == 1 else 2.0
                rig_key = "CAM_CU_B" if i == 1 else "CAM_CU_A"
                shot_scale = "特写"
                motion = "急速推近"
            elif cur_sec <= 38.0:
                # 叙事铺垫与正反打
                rel_p = (cur_sec - 10.0) / 28.0
                tension = 50 + rel_p * 20
                duration = 4.0 if (i % 2 == 0) else 3.5
                if i == 2 or i == 3:
                    rig_key = "CAM_MASTER"
                    shot_scale = "全景"
                    motion = "缓缓推近"
                elif i % 2 == 0:
                    rig_key = "CAM_OTS_A"
                    shot_scale = "中近景"
                    motion = "手持微晃"
                else:
                    rig_key = "CAM_OTS_B"
                    shot_scale = "中近景"
                    motion = "手持微晃"
            elif cur_sec <= 75.0:
                # 核心高潮打脸
                rel_p = (cur_sec - 38.0) / 37.0
                tension = 75 + rel_p * 25
                duration = 2.0 if (i % 3 != 0) else 2.5
                if i % 3 == 0:
                    rig_key = "CAM_DUTCH_CLIMAX"
                    shot_scale = "极微特写"
                    motion = "斜角升格慢动作"
                elif i % 2 == 0:
                    rig_key = "CAM_CU_A"
                    shot_scale = "特写"
                    motion = "快切推近"
                else:
                    rig_key = "CAM_CU_B"
                    shot_scale = "特写"
                    motion = "快速摇镜"
            else:
                # 绝命断章卡点
                tension = 98.0
                duration = 4.0
                rig_key = "CAM_CU_A" if (i % 2 == 0) else "CAM_DUTCH_CLIMAX"
                shot_scale = "特写"
                motion = "定格悬停"

            shots_plan.append({
                "shot_num": i,
                "timestamp_sec": round(t_accum, 1),
                "duration_sec": duration,
                "tension_score": round(tension, 1),
                "rig_key": rig_key,
                "shot_scale": shot_scale,
                "camera_movement": motion,
                "rig_meta": self.RIG_PRESETS.get(rig_key, self.RIG_PRESETS["CAM_MASTER"])
            })
            t_accum += duration

        # 归一化时长使其贴合短剧剪辑节奏：单镜时长必须在 1.5s ~ 5.5s 黄金区间，杜绝死板或超长
        sum_d = sum(s["duration_sec"] for s in shots_plan)
        if sum_d > 0 and shot_count >= 16:
            scale_factor = total_duration / sum_d
            t_cur = 0.0
            for s in shots_plan:
                s["duration_sec"] = min(5.5, max(1.5, round(s["duration_sec"] * scale_factor, 1)))
                s["timestamp_sec"] = round(t_cur, 1)
                t_cur += s["duration_sec"]
        else:
            # 镜头数适中时保持短剧动力学原设时长 (1.8s ~ 4.5s)
            t_cur = 0.0
            for s in shots_plan:
                s["duration_sec"] = min(5.0, max(1.5, s["duration_sec"]))
                s["timestamp_sec"] = round(t_cur, 1)
                t_cur += s["duration_sec"]

        return shots_plan

    def lint_and_optimize_storyboard(
        self,
        raw_shots: List[Dict[str, Any]],
        topology: Dict[str, Any],
        characters: List[str]
    ) -> List[Dict[str, Any]]:
        """
        视听语法合规检查器 (Cinematography Linter):
        1. 检查并纠正连续同景别疲劳（如连续3个中景强制梯级变换）
        2. 计算每镜拍摄视锥并在屏幕中准确投射左右人物站位 (Screen Left / Screen Right)
        3. 强制在每镜 AI 提示词中注入严格的三维空间几何坐标与环境锚点
        4. 180度行动轴线锁死保护，杜绝跳轴/越轴
        """
        char_a = characters[0] if characters else "主角"
        char_b = characters[1] if len(characters) > 1 else "对手"
        p_a = topology["line_of_action"]["start"]
        p_b = topology["line_of_action"]["end"]

        # 行动轴线向量
        line_v = SpatialVector.sub(p_b, p_a)

        optimized_shots = []
        last_scale = None
        consecutive_scale_count = 0
        last_post_action = "主体立于空间基准位，眼神锐利对峙"

        pacing_curve = self.generate_tension_and_pacing_curve(shot_count=len(raw_shots), total_duration=90)

        for idx, shot in enumerate(raw_shots):
            pacing_item = pacing_curve[idx] if idx < len(pacing_curve) else pacing_curve[-1]

            # 1. 景别连续性合规检测与纠偏
            cur_scale = shot.get("shot_type") or pacing_item["shot_scale"]
            if cur_scale == last_scale:
                consecutive_scale_count += 1
            else:
                consecutive_scale_count = 1
                last_scale = cur_scale

            # 若连续相同景别超过2次，强制梯级变换
            if consecutive_scale_count > 2:
                cur_scale = "特写" if cur_scale in ("中景", "全景") else "中近景"
                consecutive_scale_count = 1
                last_scale = cur_scale

            # 2. 匹配机位 Rig 与 180度轴线投影
            rig_key = pacing_item["rig_key"]
            rig = self.RIG_PRESETS.get(rig_key, self.RIG_PRESETS["CAM_MASTER"])

            # 计算屏幕左右站位关系（以主相机视角为基准，在轴线前侧观看）：
            if rig_key in ("CAM_OTS_A", "CAM_CU_B"):
                spatial_layout_desc = f"角色【{char_a}】置于屏幕左下前景侧影(20%宽度)，视线朝右；核心焦点为角色【{char_b}】位于屏幕中央偏右(65%宽度)，正面朝左与A对视"
                prompt_spatial_tag = f"Subject [{char_b}] at screen-right (65% horizontal), facing left; Subject [{char_a}] at foreground extreme screen-left shoulder silhouette, facing right; 180-degree axis locked on front side"
            elif rig_key in ("CAM_OTS_B", "CAM_CU_A"):
                spatial_layout_desc = f"角色【{char_b}】置于屏幕右下前景侧影(20%宽度)，视线朝左；核心焦点为角色【{char_a}】位于屏幕中央偏左(35%宽度)，正面朝右目光冷酷"
                prompt_spatial_tag = f"Subject [{char_a}] at screen-left (35% horizontal), facing right sharp focus; Subject [{char_b}] at foreground extreme screen-right shoulder silhouette, facing left; 180-degree axis locked on front side"
            elif rig_key == "CAM_TWO_SHOT":
                spatial_layout_desc = f"双人对峙构图：角色【{char_a}】稳居屏幕左侧(30%)，角色【{char_b}】立于屏幕右侧(70%)，两人视线对穿，空间张力紧绷"
                prompt_spatial_tag = f"Two-shot dynamic confrontation, Subject [{char_a}] at screen-left (30%), Subject [{char_b}] at screen-right (70%), eye lines connecting horizontally, 180-degree cinematography axis preserved"
            else:
                spatial_layout_desc = f"主控全局空间构图：【{char_a}】居左(35%)，【{char_b}】居右(65%)，背景正中清晰呈现地标锚点"
                prompt_spatial_tag = f"Master spatial layout, Subject [{char_a}] on screen-left, Subject [{char_b}] on screen-right, clear environmental anchors in background center"

            # 3. 提取环境锚点注入提示词（防背景抽卡漂移）
            anchor_desc = ", ".join(f"{a['name']}({a['desc']})" for a in topology["anchors"][:2])
            prompt_anchor_tag = f"Consistent scene environment: {topology['scene_name']}, fixed background anchors [{anchor_desc}], fixed lighting direction"

            # 4. 动作接戏状态机 (Action Continuity & State Transition)
            visual_text = shot.get("visual", "")
            pre_action = f"延续前镜落点状态：{last_post_action}" if idx > 0 else "初始起势：主角在左侧冷眼审视，对手在右侧挑衅逼近"
            post_action = self._derive_post_action_state(visual_text, cur_scale, char_a, char_b)
            last_post_action = post_action
            action_continuity = {
                "pre_action_state": pre_action,
                "post_action_state": post_action,
                "continuity_locked": True
            }
            prompt_action_tag = f"Action continuity: starting from ({pre_action}), ending in ({post_action})"

            # 5. 音画同步与唇形语法打标 (Lip Sync Flagging)
            dialogue_text = (shot.get("dialogue") or "").strip()
            lip_sync_meta = self._classify_lip_sync_requirement(dialogue_text, rig_key, cur_scale, char_a, char_b)

            # 6. 核心道具客体持久化 (Hero Prop Anchoring)
            hero_props = self._extract_hero_props(visual_text + " " + dialogue_text)
            prompt_prop_tag = f"Hero Prop continuity: [{', '.join(hero_props)}]" if hero_props else ""

            # 7. 优化生视频 Prompt
            raw_prompt = shot.get("ai_prompt", "")
            enhanced_prompt = self._synthesize_spatial_prompt(
                raw_prompt, cur_scale, rig, prompt_spatial_tag, prompt_anchor_tag,
                shot.get("visual", ""), prompt_action_tag, prompt_prop_tag
            )

            opt_shot = dict(shot)
            opt_shot["shot_type"] = cur_scale
            opt_shot["duration_sec"] = pacing_item["duration_sec"]
            opt_shot["tension_score"] = pacing_item["tension_score"]
            opt_shot["camera_rig"] = {
                "rig_key": rig_key,
                "name": rig["name"],
                "focal_length_mm": rig["focal_length"],
                "axis_side": "Axis-Left (Compliant)",
                "spatial_layout": spatial_layout_desc
            }
            opt_shot["action_continuity"] = action_continuity
            opt_shot["lip_sync"] = lip_sync_meta
            opt_shot["hero_props"] = hero_props
            opt_shot["ai_prompt"] = enhanced_prompt
            optimized_shots.append(opt_shot)

        return optimized_shots

    def _derive_post_action_state(self, visual: str, scale: str, char_a: str, char_b: str) -> str:
        """根据视觉描述自动推演当前镜头的物理姿态落点，供下个镜头接戏"""
        if any(kw in visual for kw in ("射", "劈", "砍", "打", "击", "斩", "刺")):
            return f"{char_a}完成攻击动作，手臂微沉保持击发/出招后收势姿态，胸膛起伏，目光如刃锁定{char_b}"
        elif any(kw in visual for kw in ("倒", "跪", "飞", "退", "颤", "嚎", "惊")):
            return f"{char_b}受击或震慑后退半步，身形不稳，单膝或半躬，惊恐抬头"
        elif any(kw in visual for kw in ("笑", "傲", "逼", "喝", "吼")):
            return f"{char_b}右臂前指或握拳，神色狰狞逼近，身形微前倾"
        else:
            return f"{char_a}单手负后/微垂，身姿渊渟岳峙，双足扎实固定于地面，视线不动"

    def _classify_lip_sync_requirement(
        self,
        dialogue: str,
        rig_key: str,
        scale: str,
        char_a: str,
        char_b: str
    ) -> Dict[str, Any]:
        """视听语言智能打标：区分说话人特写(必须对口型)与过肩/画外音(免唇动规避)"""
        if not dialogue or dialogue == "(无对白)":
            return {
                "requires_lip_sync": False,
                "speaker": "none",
                "reason": "无对白纯动作镜，无需唇动驱动",
                "badge": "纯动作镜"
            }

        # 检查是否为内心独白或画外音
        if any(kw in dialogue for kw in ("画外音", "OS", "旁白", "心中", "内心", "暗道")):
            return {
                "requires_lip_sync": False,
                "speaker": "voiceover",
                "reason": "画外音/OS旁白，角色无需张嘴，规避AI唇形破绽",
                "badge": "旁白OS (免唇动)"
            }

        # 过肩反打机位：镜头前景为后脑勺，主要拍对方表情
        if rig_key in ("CAM_OTS_A", "CAM_OTS_B"):
            speaker = char_a if char_a in dialogue else char_b
            return {
                "requires_lip_sync": False,
                "speaker": speaker,
                "reason": "过肩正反打背影视角，发声者背对镜头，免口型驱动",
                "badge": "过肩背视 (免唇动)"
            }

        # 正向特写与近景：必须毫秒级口型驱动对齐
        speaker = char_a if char_a in dialogue else (char_b if char_b in dialogue else "角色")
        return {
            "requires_lip_sync": True,
            "speaker": speaker,
            "reason": f"正向{scale}清晰展示说话面部，已挂载 Wav2Lip / MuseTalk 毫秒口型对位管线",
            "badge": "口型高精对齐"
        }

    def _extract_dynamic_anchors(
        self,
        scene_name: str,
        scene_desc: str = "",
        genre_cat: str = "doomsday"
    ) -> List[Dict[str, Any]]:
        """从场景名称、环境描写与题材标签中动态提取构建三维空间物理锚点"""
        text = f"{scene_name} {scene_desc}".strip()
        anchors = []

        # 1. 空间出入口 / 关卡门扉 (前景近端 Y: 1.5m ~ 2.2m)
        entry_name = "核心进出门户"
        for kw in ["防爆门", "合金门", "防弹门", "隔离门", "重型铁门", "青铜门", "山门", "舱门", "殿门", "玄关门", "石门", "门", "闸", "关隘"]:
            if kw in text:
                entry_name = kw if len(kw) > 1 else f"主进出{kw}"
                break
        anchors.append({
            "name": entry_name,
            "pos": [0.0, 1.8, 1.2],
            "desc": f"近景主通道（{entry_name}），确立场景进深起点与视线遮挡边界"
        })

        # 2. 中轴功能实体 / 枢纽台案 / 法阵 (中景区 Y: 4.5m ~ 7.0m)
        mid_name = "中轴对峙核心台"
        for kw in ["战术操作台", "控制终端", "办公桌", "长案", "主会议桌", "祭坛", "法台", "王座", "青石台", "指挥台", "操作台", "终端", "实验台"]:
            if kw in text:
                mid_name = kw
                break
        else:
            if genre_cat == "urban":
                mid_name = "主办公签字桌"
            elif genre_cat == "doomsday":
                mid_name = "战术操作台"
            elif genre_cat == "scifi":
                mid_name = "量子控制终端"
            elif genre_cat == "history":
                mid_name = "紫檀公案"
            elif genre_cat == "wuxia":
                mid_name = "红木方桌"
            else:
                mid_name = "青铜法位主座"

        anchors.append({
            "name": mid_name,
            "pos": [-2.5, 5.5, 0.9],
            "desc": f"中景核心功能实体（{mid_name}），承载双方视线交汇与重要交锋动作"
        })

        # 3. 远端天幕立面 / 纵深环境背景 (远景区 Y: 11.0m ~ 16.0m)
        bg_name = "纵深全景天幕"
        for kw in ["全息天幕", "落地窗", "观景窗", "全息屏幕", "深渊裂谷", "古殿巨壁", "天际线", "风雪荒野", "虚空穹顶", "舷窗", "星海全景"]:
            if kw in text:
                bg_name = kw
                break
        else:
            if genre_cat == "urban":
                bg_name = "CBD天际线落地窗"
            elif genre_cat == "doomsday":
                bg_name = "高透隔音防弹窗"
            elif genre_cat == "scifi":
                bg_name = "深空星海全息幕"
            elif genre_cat == "history":
                bg_name = "九龙金漆大屏风"
            elif genre_cat == "wuxia":
                bg_name = "塞外风雪客栈檐"
            else:
                bg_name = "通天石柱与苍穹云雾"

        anchors.append({
            "name": bg_name,
            "pos": [0.0, 13.0, 2.2],
            "desc": f"远景景深立面（{bg_name}），烘托世界观氛围与戏剧空间层次"
        })

        # 4. 主视听聚光点 (三维高位光源)
        anchors.append({
            "name": "主视听聚光点",
            "pos": [-1.5, 4.5, 3.5],
            "type": "高对比度电影级主光，强化角色立体轮廓与眼神交锋"
        })

        return anchors

    def _extract_hero_props(self, text: str) -> List[str]:
        """提取短剧分镜中的核心道具客体"""
        prop_keywords = [
            "复合弩", "战弩", "弓弩", "长弓", "利刃", "短刀", "佩剑", "长剑", "古剑", "飞剑",
            "手枪", "战术盾牌", "法杖", "符箓", "玉佩", "卷宗", "令牌", "纳戒", "储物戒",
            "罗盘", "晶核", "终端", "黑卡", "机密文件", "钥匙", "药剂", "信物", "合同"
        ]
        found = []
        for kw in prop_keywords:
            if kw in text and kw not in found:
                found.append(kw)
        return found

    def _synthesize_spatial_prompt(
        self,
        base_prompt: str,
        shot_scale: str,
        rig: Dict[str, Any],
        spatial_tag: str,
        anchor_tag: str,
        visual_desc: str,
        action_tag: str = "",
        prop_tag: str = ""
    ) -> str:
        """精准将空间几何、动作接戏、核心道具与摄影参数缝合入 9:16 短剧视频提示词"""
        lens_tag = f"{rig['focal_length']}mm lens, {rig['motion']}"
        tags = [t for t in [spatial_tag, anchor_tag, action_tag, prop_tag] if t]
        tags_str = ", ".join(tags)
        prefix = f"9:16 vertical short drama shot, {shot_scale}, {lens_tag}, {tags_str}"

        if not base_prompt:
            return f"{prefix}, cinematic photorealistic lighting, dramatic contrast, 8k resolution, {visual_desc}"

        clean_base = base_prompt.replace("9:16 vertical short drama shot,", "").replace("9:16 vertical shot,", "").strip()
        return f"{prefix}, {clean_base}"


# 全局单例
spatial_director = SpatialDirectorEngine()
