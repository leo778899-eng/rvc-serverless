import runpod
import os
import subprocess
import requests
import logging
from audio_separator.separator import Separator

# ==========================================
# 1. 核心配置 (根据你的实际情况调整)
# ==========================================
MODEL_URL = "https://www.toponedumps.com/wukong_v2.pth"
MODEL_NAME = "wukong_v2.pth"
INDEX_NAME = "trained_IVF3062_Flat_nprobe_1_wukong_v2_v2.index"

# ⚠️ 关键：RVC 的路径。
# 如果你是用官方 RVC Docker，通常在 /app 或 /workspace
# 这里假设 infer_cli.py 在 /app/tools/infer_cli.py 或者 /app/infer_cli.py
# 如果报错说找不到文件，你需要去 Logs 看一下 RVC 到底装在哪
RVC_INFER_SCRIPT = "/app/tools/infer_cli.py" 
# 如果你的镜像里脚本在根目录，尝试改成: "/app/infer_cli.py"

# ==========================================

BASE_DIR = "/app"
OUTPUT_DIR = "/app/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)
local_model_path = os.path.join(BASE_DIR, MODEL_NAME)
local_index_path = os.path.join(BASE_DIR, INDEX_NAME)

# === 启动检查 ===
if not os.path.exists(local_model_path):
    print(f"⬇️ 下载模型: {MODEL_URL}")
    subprocess.run(f"wget -O '{local_model_path}' '{MODEL_URL}'", shell=True)

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
        # 1. 下载
        local_song = os.path.join(OUTPUT_DIR, "input.mp3")
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
            if "Instrumental" in f: backing_path = os.path.join(OUTPUT_DIR, f)
            else: vocal_path = os.path.join(OUTPUT_DIR, f)
        print(f"✅ 分离完成: {vocal_path}")

        # 3. RVC 变声 (🔥 真·AI 推理开启)
        print(f"🤖 开始 RVC 变声 (模型: {MODEL_NAME})...")
        converted_vocal = os.path.join(OUTPUT_DIR, "converted_vocal.wav")
        
        # 构造推理命令
        # 注意：这里的参数根据标准 RVC v2 调整，不同版本可能微调
        cmd = [
            "python", RVC_INFER_SCRIPT,
            "--f0up_key", str(pitch),
            "--input_path", vocal_path,
            "--index_path", local_index_path,
            "--opt_path", converted_vocal,
            "--model_name", MODEL_NAME.replace(".pth", ""), # 通常不需要后缀
            "--device", "cuda:0",
            "--is_half", "True",
            "--filter_radius", "3",
            "--resample_sr", "0",
            "--rms_mix_rate", "0.25",
            "--protect", "0.33"
        ]
        
        # 打印命令方便调试
        print(f"执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("RVC Output:", result.stdout)

        # 4. 混音
        print("🎛️ 混音中...")
        final_mix = os.path.join(OUTPUT_DIR, "final.mp3")
        mix_cmd = f'ffmpeg -y -i "{converted_vocal}" -i "{backing_path}" -filter_complex "[0:a]volume=1.5[a1];[1:a]volume=1.0[a2];[a1][a2]amix=inputs=2:duration=longest" "{final_mix}"'
        subprocess.run(mix_cmd, shell=True, check=True)

        # 5. 上传
        print("⬆️ 上传到 Litterbox...")
        with open(final_mix, 'rb') as f:
            lb_url = "https://litterbox.catbox.moe/resources/internals/api.php"
            resp = requests.post(lb_url, data={'reqtype':'fileupload','time':'1h'}, files={'fileToUpload': f})
            if resp.status_code == 200 and resp.text.startswith("http"):
                return {"status":"success", "download_url": resp.text.strip()}
            else:
                raise Exception(f"上传失败: {resp.text}")

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

runpod.serverless.start({"handler": handler})
