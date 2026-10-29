"""
剪映专业版原生工程生成器 (Jianying Pro / CapCut Draft Exporter)
自动将分镜数据组装导出为剪映原生多轨工程文件 (draft_content.json + draft_meta_info.json):
- 视频轨 (Video Track): 9:16 竖屏视频片段顺序排布
- 对白轨 (Audio Dialogue Track): Edge-TTS 高清配音文件对齐
- 音效重音轨 (Audio SFX Track): 氛围、打脸重音、环境底噪
- 智能字幕轨 (Text Subtitle Track): 对白台词毫秒级贴合字幕
"""

import json
import uuid
import time
import zipfile
import io
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
        text_track_id = cls._gen_id()

        total_duration_micros = 0
        video_segments = []
        audio_segments = []
        sfx_segments = []
        text_segments = []

        materials_videos = []
        materials_audios = []
        materials_texts = []
        materials_speeds = []

        current_time_micros = 0

        for idx, shot in enumerate(shots):
            shot_num = shot.get("shot_num", idx + 1)
            duration_sec = float(shot.get("duration_sec", 3.0))
            shot_duration_micros = int(duration_sec * MICROS_PER_SEC)

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
            video_segments.append({
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
            })

            # 3. 对白轨物料与片段 (若有对白台词)
            dialogue = (shot.get("dialogue") or "").strip()
            if dialogue and dialogue != "(无对白)":
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

                # 4. 字幕文本物料与片段
                text_mat_id = cls._gen_id()
                materials_texts.append({
                    "alignment": 1,
                    "background_alpha": 0.0,
                    "bold": True,
                    "content": f"<color=#FFFFFF>{dialogue}</color>",
                    "font_size": 8.0,
                    "id": text_mat_id,
                    "line_spacing": 0.02,
                    "type": "text"
                })

                text_seg_id = cls._gen_id()
                text_segments.append({
                    "clip": {
                        "alpha": 1.0,
                        "rotation": 0.0,
                        "scale": {"x": 1.0, "y": 1.0},
                        "transform": {"x": 0.0, "y": -0.72} # 竖屏底部黄金字幕位
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
                    "volume": 0.8
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
                "id": text_track_id,
                "is_default_name": False,
                "name": "智能台词字幕轨",
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
            "id": draft_id,
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
                "drafts": [],
                "effects": [],
                "flowers": [],
                "green_screens": [],
                "handwrites": [],
                "hsl": [],
                "images": [],
                "log_color_wheels": [],
                "manual_deformations": [],
                "masks": [],
                "material_animations": [],
                "material_colors": [],
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
                "transitions": [],
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

【如何导入剪映专业版】：
1. 打开电脑中的剪映草稿目录：
   - Windows 路径：
     C:\\Users\\<用户名>\\AppData\\Local\\JianyingPro\\User Data\\Projects\\com.lveditor.draft\\
   - macOS 路径：
     ~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/
2. 将本压缩包解压后的文件夹【{draft_name}】直接复制粘贴进上述目录。
3. 打开剪映专业版，在草稿列表中即可看到《{draft_name}》！
4. 双击打开，视频轨、TTS对白轨、重音音效轨、智能台词字幕轨已全部精确对齐！
"""
            zf.writestr(f"{draft_name}/导入说明.txt", readme_text)

        return buf.getvalue()
