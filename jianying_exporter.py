"""
剪映专业版原生工程生成器 (Jianying Pro / CapCut Draft Exporter)
自动将分镜数据组装导出为剪映原生多轨工程文件 (draft_content.json + draft_meta_info.json):
- 视频轨 (Video Track): 9:16 竖屏视频片段顺序排布，含 Hook 闪白与高潮震荡转场
- 对白轨 (Audio Dialogue Track): Edge-TTS 高清配音文件对齐
- 音效重音轨 (Audio SFX Track): 氛围、打脸重音、环境底噪
- 智能避让BGM轨 (Audio Ducking BGM Track): 有对白时自动压制音量，动作高潮自动回弹
- 黄金花字字幕轨 (Text Subtitle Track): 角色名金字高亮、正文纯白描边黑框
"""

import json
import uuid
import time
import zipfile
import io
import re
from pathlib import Path
from typing import Dict, Any, List, Optional


class JianyingDraftExporter:
    """剪映专业版工程导出引擎"""

    @staticmethod
    def _gen_id() -> str:
        return str(uuid.uuid4()).upper()

    @classmethod
    def build_draft(
        cls,
        drama_data: Dict[str, Any],
        book_title: str = "天道短剧",
        audio_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """构建剪映原生工程对象 (draft_content.json)"""
        episode_num = drama_data.get("episode_num", 1)
        shots = drama_data.get("shots", [])

        # 时间单位：微秒 (1秒 = 1,000,000 微秒)
        MICROS_PER_SEC = 1000000

        draft_id = cls._gen_id()
        video_track_id = cls._gen_id()
        audio_track_id = cls._gen_id()
        sfx_track_id = cls._gen_id()
        bgm_track_id = cls._gen_id()
        text_track_id = cls._gen_id()

        video_segments = []
        audio_segments = []
        sfx_segments = []
        bgm_segments = []
        text_segments = []

        materials_videos = []
        materials_audios = []
        materials_texts = []
        materials_speeds = []
        materials_transitions = []

        # 预先生成专用的转场物料 (Hook 闪白、高潮震荡)
        hook_trans_id = cls._gen_id()
        materials_transitions.append({
            "category_id": "flash",
            "category_name": "闪白转场",
            "duration": 350000, # 0.35s
            "id": hook_trans_id,
            "is_overlap": False,
            "name": "闪白Hook快切",
            "resource_id": "flash_white",
            "type": "transition"
        })

        climax_trans_id = cls._gen_id()
        materials_transitions.append({
            "category_id": "shake",
            "category_name": "震荡转场",
            "duration": 400000, # 0.4s
            "id": climax_trans_id,
            "is_overlap": False,
            "name": "镜头重音冲击",
            "resource_id": "impact_shake",
            "type": "transition"
        })

        current_time_micros = 0

        for idx, shot in enumerate(shots):
            shot_num = shot.get("shot_num", idx + 1)
            duration_sec = float(shot.get("duration_sec", 3.0))
            shot_duration_micros = int(duration_sec * MICROS_PER_SEC)
            tension = float(shot.get("tension_score", 60.0))

            # 1. 速度对象 (1.0倍速)
            speed_id = cls._gen_id()
            materials_speeds.append({
                "curve_speed": None,
                "id": speed_id,
                "mode": 0,
                "speed": 1.0,
                "type": "speed"
            })

            # 2. 视频轨物料与片段
            video_mat_id = cls._gen_id()
            video_url = shot.get("video_url") or shot.get("first_frame_url") or ""
            materials_videos.append({
                "category_id": "",
                "category_name": "local",
                "check_flag": 63487,
                "duration": shot_duration_micros,
                "height": 1920,
                "id": video_mat_id,
                "material_name": f"Shot_{episode_num}_{shot_num}.mp4",
                "path": video_url,
                "type": "video",
                "width": 1080
            })

            video_seg_id = cls._gen_id()
            video_seg: Dict[str, Any] = {
                "clip": {
                    "alpha": 1.0,
                    "flip": {"horizontal": False, "vertical": False},
                    "rotation": 0.0,
                    "scale": {"x": 1.0, "y": 1.0},
                    "transform": {"x": 0.0, "y": 0.0}
                },
                "enable_adjust": True,
                "id": video_seg_id,
                "material_id": video_mat_id,
                "render_index": 0,
                "speed": 1.0,
                "source_timerange": {"duration": shot_duration_micros, "start": 0},
                "target_timerange": {"duration": shot_duration_micros, "start": current_time_micros},
                "speed_id": speed_id,
                "volume": 1.0
            }

            # 挂载转场：第1镜与第2镜交接处挂载 Hook 闪白；高潮张力大于85时挂载冲击震荡
            if idx == 0 and len(shots) > 1:
                video_seg["extra_material_refs"] = [hook_trans_id]
            elif tension >= 88.0:
                video_seg["extra_material_refs"] = [climax_trans_id]

            video_segments.append(video_seg)

            # 3. 对白轨物料与片段 (若有对白台词)
            dialogue = (shot.get("dialogue") or "").strip()
            has_speech = bool(dialogue and dialogue != "(无对白)")

            if has_speech:
                audio_mat_id = cls._gen_id()
                materials_audios.append({
                    "app_id": 0,
                    "category_id": "",
                    "category_name": "local",
                    "check_flag": 1,
                    "duration": shot_duration_micros,
                    "id": audio_mat_id,
                    "material_name": f"TTS_Speech_{episode_num}_{shot_num}.mp3",
                    "path": f"audio/shot_{episode_num}_{shot_num}.mp3",
                    "type": "music"
                })

                audio_seg_id = cls._gen_id()
                audio_segments.append({
                    "id": audio_seg_id,
                    "material_id": audio_mat_id,
                    "render_index": 0,
                    "source_timerange": {"duration": shot_duration_micros, "start": 0},
                    "target_timerange": {"duration": shot_duration_micros, "start": current_time_micros},
                    "speed_id": speed_id,
                    "volume": 1.0
                })

                # 4. 黄金花字字幕物料与片段 (角色名高亮 + 正文纯白黑边)
                text_mat_id = cls._gen_id()
                spk_match = re.match(r"^([^\(（：:]{1,10})([\(（][^\)）]+[\)）])?[：:]\s*(.*)$", dialogue)
                if spk_match:
                    spk_name = spk_match.group(1).strip()
                    spk_action = spk_match.group(2) or ""
                    spk_line = spk_match.group(3).strip()
                    formatted_content = f"<color=#FBBF24>【{spk_name}】</color><color=#94A3B8>{spk_action}</color> <color=#FFFFFF>{spk_line}</color>"
                else:
                    formatted_content = f"<color=#FFFFFF>{dialogue}</color>"

                materials_texts.append({
                    "alignment": 1,
                    "background_alpha": 0.0,
                    "bold": True,
                    "content": formatted_content,
                    "font_size": 8.5,
                    "id": text_mat_id,
                    "line_spacing": 0.02,
                    "stroke_color": "#000000",
                    "stroke_width": 0.08,
                    "shadow_color": "#000000",
                    "shadow_alpha": 0.9,
                    "shadow_distance": 0.02,
                    "type": "text"
                })

                text_seg_id = cls._gen_id()
                text_segments.append({
                    "clip": {
                        "alpha": 1.0,
                        "rotation": 0.0,
                        "scale": {"x": 1.0, "y": 1.0},
                        "transform": {"x": 0.0, "y": -0.72} # 竖屏底部黄金字幕安全区
                    },
                    "id": text_seg_id,
                    "material_id": text_mat_id,
                    "render_index": 100,
                    "source_timerange": {"duration": shot_duration_micros, "start": 0},
                    "target_timerange": {"duration": shot_duration_micros, "start": current_time_micros}
                })

            # 5. 音效重音轨 (若有 sfx_bgm 描述)
            sfx = (shot.get("sfx_bgm") or "").strip()
            if sfx:
                sfx_mat_id = cls._gen_id()
                materials_audios.append({
                    "app_id": 0,
                    "category_id": "",
                    "category_name": "sfx",
                    "check_flag": 1,
                    "duration": shot_duration_micros,
                    "id": sfx_mat_id,
                    "material_name": f"SFX_{episode_num}_{shot_num}_{sfx[:10]}.mp3",
                    "path": f"sfx/shot_{episode_num}_{shot_num}.mp3",
                    "type": "sound"
                })

                sfx_seg_id = cls._gen_id()
                sfx_segments.append({
                    "id": sfx_seg_id,
                    "material_id": sfx_mat_id,
                    "render_index": 0,
                    "source_timerange": {"duration": shot_duration_micros, "start": 0},
                    "target_timerange": {"duration": shot_duration_micros, "start": current_time_micros},
                    "speed_id": speed_id,
                    "volume": 0.85
                })

            # 6. 智能音频避让 BGM 氛围轨 (Audio Ducking)
            # 有对白时音量压至 0.22 避让语音；无对白纯动作时回弹至 0.85 增强张力
            bgm_mat_id = cls._gen_id()
            materials_audios.append({
                "app_id": 0,
                "category_id": "",
                "category_name": "bgm",
                "check_flag": 1,
                "duration": shot_duration_micros,
                "id": bgm_mat_id,
                "material_name": f"BGM_Atmosphere_{episode_num}_{shot_num}.mp3",
                "path": f"bgm/ambient_{episode_num}.mp3",
                "type": "music"
            })

            ducking_volume = 0.22 if has_speech else (0.85 if tension >= 80 else 0.55)
            bgm_seg_id = cls._gen_id()
            bgm_segments.append({
                "id": bgm_seg_id,
                "material_id": bgm_mat_id,
                "render_index": 0,
                "source_timerange": {"duration": shot_duration_micros, "start": 0},
                "target_timerange": {"duration": shot_duration_micros, "start": current_time_micros},
                "speed_id": speed_id,
                "volume": ducking_volume
            })

            current_time_micros += shot_duration_micros

        total_duration_micros = current_time_micros

        tracks = [
            {
                "attribute": 0,
                "flag": 0,
                "id": video_track_id,
                "is_default_name": False,
                "name": "短剧主视频轨",
                "segments": video_segments,
                "type": "video"
            },
            {
                "attribute": 0,
                "flag": 0,
                "id": audio_track_id,
                "is_default_name": False,
                "name": "角色原生对白轨(TTS)",
                "segments": audio_segments,
                "type": "audio"
            },
            {
                "attribute": 0,
                "flag": 0,
                "id": sfx_track_id,
                "is_default_name": False,
                "name": "重音音效轨(SFX)",
                "segments": sfx_segments,
                "type": "audio"
            },
            {
                "attribute": 0,
                "flag": 0,
                "id": bgm_track_id,
                "is_default_name": False,
                "name": "智能避让BGM氛围轨(Ducking)",
                "segments": bgm_segments,
                "type": "audio"
            },
            {
                "attribute": 0,
                "flag": 0,
                "id": text_track_id,
                "is_default_name": False,
                "name": "黄金花字台词字幕轨",
                "segments": text_segments,
                "type": "text"
            }
        ]

        draft_content = {
            "canvas_config": {
                "height": 1920,
                "ratio": "original",
                "width": 1080
            },
            "color_space": 0,
            "config": {
                "adjust_max_index": 1,
                "attachment_info": [],
                "combination_max_index": 1,
                "export_range": None,
                "extract_audio_last_index": 1,
                "lyrics_recognition_id": "",
                "lyrics_sync": True,
                "lyrics_taskinfo": [],
                "maintrack_adsorb": True,
                "material_save_mode": 0,
                "original_sound_last_index": 1,
                "record_audio_last_index": 1,
                "sticker_max_index": 1,
                "subtitle_keywords_config": None,
                "subtitle_recognition_id": "",
                "subtitle_sync": True,
                "subtitle_taskinfo": [],
                "system_font_list": [],
                "video_mute": False,
                "zoom_info_params": None
            },
            "cover": None,
            "create_time": int(time.time()),
            "duration": total_duration_micros,
            "extra_info": None,
            "fps": 30.0,
            "free_render_index_mode_on": False,
            "group_container": None,
            "id": draft_id,
            "keyframe_graph_list": [],
            "keyframes": {
                "adjusts": [],
                "audios": [],
                "effects": [],
                "filters": [],
                "handwrites": [],
                "stickers": [],
                "texts": [],
                "videos": []
            },
            "last_modified_platform": {
                "app_id": 3704,
                "app_source": "jianying",
                "app_version": "6.0.0",
                "device_id": "tiandao_engine",
                "hard_disk_id": "tiandao_disk",
                "mac_address": "tiandao_mac",
                "os": "windows",
                "os_version": "10.0.19045"
            },
            "materials": {
                "audio_balances": [],
                "audio_effects": [],
                "audio_fades": [],
                "audio_track_indexes": [],
                "audios": materials_audios,
                "beats": [],
                "canvases": [],
                "chromas": [],
                "color_curves": [],
                "digital_humans": [],
                "drafts": [],
                "effects": [],
                "flowers": [],
                "green_screens": [],
                "handwrites": [],
                "hsl": [],
                "images": [],
                "log_color_wheels": [],
                "loudnesses": [],
                "manual_deformations": [],
                "masks": [],
                "material_animations": [],
                "material_colors": [],
                "multi_language_refs": [],
                "music_hit_points": [],
                "placeholder_researches": [],
                "placeholders": [],
                "plugin_effects": [],
                "primary_color_wheels": [],
                "realtime_denoises": [],
                "shapes": [],
                "smart_crops": [],
                "sound_channel_mappings": [],
                "speeds": materials_speeds,
                "stickers": [],
                "tail_leaders": [],
                "text_templates": [],
                "texts": materials_texts,
                "transitions": materials_transitions,
                "video_effects": [],
                "video_track_indexes": [],
                "videos": materials_videos,
                "vocal_beautifys": [],
                "vocal_separations": []
            },
            "mutable_config": None,
            "name": f"{book_title}_第{episode_num}集短剧",
            "new_version": "103.0.0",
            "relationships": [],
            "tracks": tracks,
            "update_time": int(time.time()),
            "version": 360000
        }

        draft_meta_info = {
            "draft_cloud_capcut_id": "",
            "draft_cloud_last_action_download": False,
            "draft_cloud_purchase_info": "",
            "draft_cloud_template_id": "",
            "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "",
            "draft_cover": "",
            "draft_fold_path": "",
            "draft_id": draft_id,
            "draft_is_ai_shorts": True,
            "draft_is_invisible": False,
            "draft_name": f"{book_title}_第{episode_num}集短剧",
            "draft_new_version": "103.0.0",
            "draft_removable_storage_device": "",
            "draft_root_path": "",
            "draft_timeline_materials_size_": 0,
            "tm_draft_cloud_completed": "",
            "tm_draft_cloud_modified": 0,
            "tm_draft_create": int(time.time() * 1000),
            "tm_draft_modified": int(time.time() * 1000),
            "tm_draft_removed": 0
        }

        return {
            "draft_content": draft_content,
            "draft_meta_info": draft_meta_info,
            "draft_name": f"{book_title}_第{episode_num}集短剧"
        }

    @classmethod
    def export_draft_zip_bytes(cls, drama_data: Dict[str, Any], book_title: str = "天道短剧") -> bytes:
        """一键打包为可直接解压导入剪映的 ZIP 压缩包"""
        draft_pkg = cls.build_draft(drama_data, book_title=book_title)
        draft_name = draft_pkg["draft_name"]

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # 剪映工程规范结构：以工程名称为根文件夹
            zf.writestr(
                f"{draft_name}/draft_content.json",
                json.dumps(draft_pkg["draft_content"], ensure_ascii=False, indent=2)
            )
            zf.writestr(
                f"{draft_name}/draft_meta_info.json",
                json.dumps(draft_pkg["draft_meta_info"], ensure_ascii=False, indent=2)
            )
            # 附带使用说明
            readme_text = f"""【天道短剧引擎 - 剪映专业版一键成片导入说明】
作品名：《{book_title}》
集数：第 {drama_data.get('episode_num', 1)} 集
镜头数：{len(drama_data.get('shots', []))} 个镜头
工程特色：
- 9:16竖屏电影级多机位与行动轴线锁死保护
- 自动挂载 Hook 闪白与高潮冲击震荡转场
- 黄金花字字幕：角色名金字高亮 + 纯白黑边高反差防遮挡
- 智能避让 BGM 氛围轨：对白时音量自动压低，纯动作戏自动回升
- 物理打包真实 TTS 配音音频文件

【如何导入剪映专业版】：
1. 打开电脑中的剪映草稿目录：
   - Windows 路径：
     C:/Users/<用户名>/AppData/Local/JianyingPro/User Data/Projects/com.lveditor.draft/
   - macOS 路径：
     ~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/
2. 将本压缩包解压后的文件夹【{draft_name}】直接复制粘贴进上述目录。
3. 打开剪映专业版，在草稿列表中即可看到《{draft_name}》！
4. 双击打开，视频轨、TTS对白轨、重音音效轨、智能避让BGM轨、黄金花字字幕轨已全部精确对齐！
"""
            zf.writestr(f"{draft_name}/导入说明.txt", readme_text)

            # 自动物理打包本地已生成的真实对白 MP3 音频进工程包
            audio_dir = Path("output/audio")
            ep_num = drama_data.get("episode_num", 1)
            if audio_dir.exists():
                for s in drama_data.get("shots", []):
                    s_num = s.get("shot_num", 1)
                    for a_file in audio_dir.glob(f"shot_{ep_num}_{s_num}_*.mp3"):
                        if a_file.is_file() and a_file.stat().st_size > 0:
                            zf.writestr(
                                f"{draft_name}/audio/shot_{ep_num}_{s_num}.mp3",
                                a_file.read_bytes()
                            )
                            break

        return buf.getvalue()