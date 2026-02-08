import runpod
import os
import subprocess
import requests
import logging
from audio_separator.separator import Separator

# ==========================================
# 🛑 暴力补丁区域 (Force Install)
# 不管缺不缺，上来先装一遍，专治各种不服
# ==========================================
print("🚑 正在强制修复运行环境... (Force Installing Dependencies)")
try:
    # 强制安装 av, fairseq, faiss-cpu, numpy
    # 这里的 -q 是静默安装，--no-cache-dir 避免缓存问题
    subprocess.run("pip install av fairseq faiss-cpu numpy --upgrade --no-cache-dir", shell=True, check=True)
    print("✅ 暴力修复完成！依赖已安装。")
except Exception as e:
    print(f"⚠️ 修复过程遇到小问题 (通常可忽略): {e}")

# ==========================================
# 1. 核心配置
# ==========================================
MODEL_URL = "https://www.toponedumps.com/wukong_v2.pth"
MODEL_NAME = "wukong_v2.pth" 
INDEX_NAME = "trained_IVF3062_Flat_nprobe_1_wukong_v2_v2.index"

RVC_GIT_URL = "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git"
RVC_DIR = "/app/RVC_Code"  
WEIGHTS_DIR = os.path.join(RVC_DIR, "weights")

# ==========================================

BASE_DIR = "/app"
OUTPUT_DIR = "/app/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(WEIGHTS_DIR, exist_ok=True)

# 1. 检查并下载 RVC 代码 (如果代码文件夹不存在)
if not os.path.exists(os.path.join(RVC_DIR, "tools", "infer_cli.py")):
    print("🚀 未检测到 RVC 代码，正在从 GitHub 克隆...")
    try:
        subprocess.run(f"git clone {RVC_GIT_URL} {RVC_DIR}", shell=True, check=True)
        print("✅ RVC 代码下载完成！")
    except Exception as e:
        print(f"❌ RVC 代码下载失败: {e}")
else:
    print("✅ RVC 代码已存在，跳过下载。")

# ==========================================

local_model_path = os.path.join(WEIGHTS_DIR, MODEL_NAME)
local_index_path = os.path.join(BASE_DIR, INDEX_NAME)
RVC_INFER_SCRIPT = os.path.join(RVC_DIR, "tools", "infer_cli.py")

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

        # 3. RVC 变声
        print(f"🤖 开始 RVC 变声 (脚本: {RVC_INFER_SCRIPT})...")
        converted_vocal = os.path.join(OUTPUT_DIR, "converted_vocal.wav")
        
        cwd = RVC_DIR 
        
        cmd = [
            "python", RVC_INFER_SCRIPT,
            "--f0up_key", str(pitch),
            "--input_path", vocal_path,
            "--index_path", local_index_path,
            "--f0method", "rmvpe",
            "--opt_path", converted_vocal,
            "--model_name", MODEL_NAME.replace(".pth", ""),
            "--index_rate", "0.7",
            "--device", "cuda:0",
            "--is_half", "True",
            "--filter_radius", "3",
            "--resample_sr", "0",
            "--rms_mix_rate", "0.25",
            "--protect", "0.33"
        ]
        
        print(f"执行命令: {' '.join(cmd)}")
        # cwd参数很关键，让 Python 在 RVC 目录下运行
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=cwd)
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

    except subprocess.CalledProcessError as e:
        print(f"❌ RVC Error:\n{e.stderr}")
        return {"status": "error", "message": f"RVC Failed: {e.stderr}"}
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

runpod.serverless.start({"handler": handler})
