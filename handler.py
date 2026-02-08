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

# 定义 RVC 代码仓库地址 (使用官方或稳定的 Fork)
RVC_GIT_URL = "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git"
RVC_DIR = "/app/RVC_Code"  # 我们把代码下载到这里

# ==========================================

BASE_DIR = "/app"
OUTPUT_DIR = "/app/output"
WEIGHTS_DIR = os.path.join(RVC_DIR, "weights") # ⚠️ 模型必须放在 RVC 代码目录下的 weights 里
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1. 检查并下载 RVC 代码 (如果没有的话) 🛠️
if not os.path.exists(os.path.join(RVC_DIR, "tools", "infer_cli.py")):
    print("🚀 未检测到 RVC 代码，正在从 GitHub 克隆...")
    try:
        # 克隆代码
        subprocess.run(f"git clone {RVC_GIT_URL} {RVC_DIR}", shell=True, check=True)
        print("✅ RVC 代码下载完成！")
        
        # 安装依赖 (这一步可能比较慢，但只需要跑一次)
        print("📦 正在安装 RVC 依赖...")
        subprocess.run(f"pip install -r {RVC_DIR}/requirements.txt", shell=True)
    except Exception as e:
        print(f"❌ RVC 代码下载失败: {e}")
else:
    print("✅ RVC 代码已存在。")

# 重新定义路径
local_model_path = os.path.join(WEIGHTS_DIR, MODEL_NAME)
local_index_path = os.path.join(BASE_DIR, INDEX_NAME)
# 脚本路径现在确定了
RVC_INFER_SCRIPT = os.path.join(RVC_DIR, "tools", "infer_cli.py")

# 确保 weights 目录存在
os.makedirs(WEIGHTS_DIR, exist_ok=True)

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
        
        # ⚠️ 必须切换工作目录到 RVC 文件夹，否则找不到 config
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
