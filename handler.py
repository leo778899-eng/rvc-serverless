import runpod
import os
import subprocess
import requests
import logging
from audio_separator.separator import Separator

# ==========================================
# 1. 核心配置
# ==========================================
MODEL_URL = "https://www.toponedumps.com/wukong_v2.pth"
MODEL_NAME = "wukong_v2.pth"
INDEX_NAME = "trained_IVF3062_Flat_nprobe_1_wukong_v2_v2.index"
# ==========================================

# 初始化路径
BASE_DIR = "/app"
OUTPUT_DIR = "/app/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

local_model_path = os.path.join(BASE_DIR, MODEL_NAME)
local_index_path = os.path.join(BASE_DIR, INDEX_NAME)

# === 启动检查 ===
print(f"🔄 系统启动中... 正在检查模型文件...")
if not os.path.exists(local_model_path):
    print(f"⬇️ 正在从服务器下载模型: {MODEL_URL}")
    try:
        subprocess.run(f"wget -O '{local_model_path}' '{MODEL_URL}'", shell=True, check=True)
        print("✅ 模型下载完成！")
    except Exception as e:
        print(f"❌ 模型下载失败: {e}")
else:
    print("✅ 模型已存在。")

def download_file(url, filename):
    print(f"⬇️ 正在下载音频: {url}")
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        return filename
    except Exception as e:
        raise Exception(f"音频下载失败: {e}")

def handler(job):
    job_input = job["input"]
    song_url = job_input.get("song_url")
    pitch = job_input.get("pitch", 0) 
    
    if not song_url:
        return {"error": "❌ 请提供 song_url 参数"}

    try:
        # 1. 下载
        local_song = os.path.join(OUTPUT_DIR, "input_song.mp3")
        download_file(song_url, local_song)
        print("✅ 歌曲下载成功")

        # 2. UVR5 分离
        print("✂️ 开始 UVR5 分离...")
        separator = Separator(log_level=logging.INFO, output_dir=OUTPUT_DIR)
        separator.load_model(model_filename='UVR-MDX-NET-Inst_HQ_3.onnx')
        output_files = separator.separate(local_song)
        
        backing_path = None
        vocal_path = None
        for f in output_files:
            if "Instrumental" in f:
                backing_path = os.path.join(OUTPUT_DIR, f)
            else:
                vocal_path = os.path.join(OUTPUT_DIR, f)
        print(f"✅ 分离完成: 人声={vocal_path}, 伴奏={backing_path}")

        # 3. RVC 变声 (模拟)
        print(f"🤖 开始 RVC 变声处理...")
        converted_vocal = os.path.join(OUTPUT_DIR, "converted_vocal.wav")
        subprocess.run(f"cp '{vocal_path}' '{converted_vocal}'", shell=True)

        # 4. 混音
        print("🎛️ 正在合成最终音频...")
        final_mix = os.path.join(OUTPUT_DIR, "final_result.mp3")
        cmd = f'ffmpeg -y -i "{converted_vocal}" -i "{backing_path}" -filter_complex "[0:a]volume=1.5[a1];[1:a]volume=1.0[a2];[a1][a2]amix=inputs=2:duration=longest" "{final_mix}"'
        subprocess.run(cmd, shell=True, check=True)

        # ======================================================
        # 5. 上传结果 (✅ 改用 Litterbox，不再解析JSON，纯文本更稳定)
        # ======================================================
        print("⬆️ 上传最终作品到 Litterbox ...")
        
        with open(final_mix, 'rb') as f:
            # Litterbox API 很简单，上传成功直接返回 URL 字符串
            lb_url = "https://litterbox.catbox.moe/resources/internals/api.php"
            payload = {'reqtype': 'fileupload', 'time': '1h'} # 文件保留1小时
            files = {'fileToUpload': f}
            
            response = requests.post(lb_url, data=payload, files=files)
            
            # 这里关键：我们不解析 JSON，直接拿 text
            if response.status_code == 200 and response.text.startswith("http"):
                download_link = response.text.strip()
                print(f"✅ 上传成功: {download_link}")
            else:
                # 如果失败，打印出对方到底返回了什么，方便调试
                print(f"❌ 上传失败内容: {response.text}")
                raise Exception(f"Litterbox 上传失败: {response.status_code}")

        return {
            "status": "success",
            "message": "AI 翻唱处理完成！",
            "download_url": download_link,
            "note": "⚠️ 链接有效期 1 小时，请尽快下载"
        }

    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

runpod.serverless.start({"handler": handler})
