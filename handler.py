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
MODEL_NAME = "wukong_v2.pth" # 不要带路径，只要名字
INDEX_NAME = "trained_IVF3062_Flat_nprobe_1_wukong_v2_v2.index"

# RVC 推理脚本路径 (根据你的镜像实际情况，可能是 tools/infer_cli.py)
# 如果报错找不到文件，请确认你的 Docker 镜像里 RVC 装在哪
RVC_INFER_SCRIPT = "/app/tools/infer_cli.py" 

# ==========================================

BASE_DIR = "/app"
OUTPUT_DIR = "/app/output"
# ⚠️ 关键修正：RVC 默认在 weights 文件夹找模型，必须建这个文件夹
WEIGHTS_DIR = "/app/weights" 
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(WEIGHTS_DIR, exist_ok=True)

# 模型必须下载到 weights 目录
local_model_path = os.path.join(WEIGHTS_DIR, MODEL_NAME)
local_index_path = os.path.join(BASE_DIR, INDEX_NAME)

# === 启动检查 ===
print(f"🔄 系统启动... 检查模型...")
if not os.path.exists(local_model_path):
    print(f"⬇️ 下载模型到 weights 目录: {MODEL_URL}")
    # 这里的 -O 参数确保文件存到 weights/wukong_v2.pth
    subprocess.run(f"wget -O '{local_model_path}' '{MODEL_URL}'", shell=True, check=True)
else:
    print("✅ 模型已在 weights 目录中。")

def download_file(url, filename):
    try:
        response = requests.get(url, stream=True, timeout=60)
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
    except Exception as e:
        raise Exception(f"下载失败: {e}")

def handler(job):
    job_input = job["input"]
    song_url = job_input.get("song_url")
    pitch = job_input.get("pitch", 0) 
    
    if not song_url: return {"error": "❌ 请提供 song_url"}

    try:
        # 1. 下载歌曲
        local_song = os.path.join(OUTPUT_DIR, "input_song.mp3")
        download_file(song_url, local_song)
        print("✅ 歌曲下载成功")

        # 2. UVR5 分离 (分离人声和伴奏)
        print("✂️ 开始 UVR5 分离...")
        separator = Separator(log_level=logging.INFO, output_dir=OUTPUT_DIR)
        separator.load_model(model_filename='UVR-MDX-NET-Inst_HQ_3.onnx')
        output_files = separator.separate(local_song)
        
        backing_path = None
        vocal_path = None
        for f in output_files:
            if "Instrumental" in f: backing_path = os.path.join(OUTPUT_DIR, f)
            else: vocal_path = os.path.join(OUTPUT_DIR, f)
        print(f"✅ 分离完成: {vocal_path}")

        # 3. RVC 变声 (🔥 关键修正部分)
        print(f"🤖 开始 RVC 变声 (模型: {MODEL_NAME})...")
        converted_vocal = os.path.join(OUTPUT_DIR, "converted_vocal.wav")
        
        # 构造推理命令 (补全了缺失的参数)
        cmd = [
            "python", RVC_INFER_SCRIPT,
            "--f0up_key", str(pitch),
            "--input_path", vocal_path,
            "--index_path", local_index_path,
            "--f0method", "rmvpe",        # <--- 之前漏了这个！必须指定算法
            "--opt_path", converted_vocal,
            "--model_name", MODEL_NAME.replace(".pth", ""), # RVC 只要名字，它自己会去 weights 找
            "--index_rate", "0.7",        # <--- 建议加上，控制相似度
            "--device", "cuda:0",
            "--is_half", "True",
            "--filter_radius", "3",
            "--resample_sr", "0",
            "--rms_mix_rate", "0.25",
            "--protect", "0.33"
        ]
        
        print(f"执行 RVC 命令: {' '.join(cmd)}")
        # capture_output=True 可以让我们在日志里看到 RVC 内部具体的报错
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("RVC 输出日志:", result.stdout)

        # 4. 混音
        print("🎛️ 混音中...")
        final_mix = os.path.join(OUTPUT_DIR, "final.mp3")
        mix_cmd = f'ffmpeg -y -i "{converted_vocal}" -i "{backing_path}" -filter_complex "[0:a]volume=1.5[a1];[1:a]volume=1.0[a2];[a1][a2]amix=inputs=2:duration=longest" "{final_mix}"'
        subprocess.run(mix_cmd, shell=True, check=True)

        # 5. 上传 (Litterbox)
        print("⬆️ 上传到 Litterbox...")
        with open(final_mix, 'rb') as f:
            lb_url = "https://litterbox.catbox.moe/resources/internals/api.php"
            resp = requests.post(lb_url, data={'reqtype':'fileupload','time':'1h'}, files={'fileToUpload': f})
            if resp.status_code == 200 and resp.text.startswith("http"):
                return {"status":"success", "download_url": resp.text.strip()}
            else:
                raise Exception(f"上传失败: {resp.text}")

    except subprocess.CalledProcessError as e:
        # 如果 RVC 命令失败，打印它的标准错误输出，这样我们就能看到具体原因
        print(f"❌ RVC 命令执行失败! 错误详情:\n{e.stderr}")
        return {"status": "error", "message": f"RVC Error: {e.stderr}"}
    except Exception as e:
        print(f"❌ 系统错误: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

runpod.serverless.start({"handler": handler})
