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
# 2. 自动寻找 RVC 脚本 (关键修复功能) 🕵️‍♂️
# ==========================================
def find_rvc_script():
    # 这里列出所有可能的藏身之处
    possible_paths = [
        "/app/tools/infer_cli.py",
        "/app/infer_cli.py",             # 很多镜像直接放在根目录
        "/workspace/tools/infer_cli.py",
        "/workspace/infer_cli.py",
        "/app/RVC/tools/infer_cli.py",
        "/tools/infer_cli.py"
    ]
    
    print("🔍 正在自动寻找 RVC 推理脚本...")
    for path in possible_paths:
        if os.path.exists(path):
            print(f"✅ 找到了！脚本路径是: {path}")
            return path
    
    # 如果都找不到，打印当前目录结构帮我们调试
    print("❌ 没找到 infer_cli.py！正在打印 /app 目录结构供调试:")
    for root, dirs, files in os.walk("/app"):
        for file in files:
            print(os.path.join(root, file))
    return None

# 获取脚本路径
RVC_INFER_SCRIPT = find_rvc_script()

# ==========================================

BASE_DIR = "/app"
OUTPUT_DIR = "/app/output"
WEIGHTS_DIR = "/app/weights" 
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(WEIGHTS_DIR, exist_ok=True)

local_model_path = os.path.join(WEIGHTS_DIR, MODEL_NAME)
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
    # 如果启动时没找到脚本，这里直接报错并打印目录
    if not RVC_INFER_SCRIPT:
        return {"status": "error", "message": "❌ 严重错误: 无法找到 infer_cli.py，请查看日志里的文件列表"}

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

    except subprocess.CalledProcessError as e:
        print(f"❌ RVC Error Detail:\n{e.stderr}")
        return {"status": "error", "message": f"RVC Failed: {e.stderr}"}
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

runpod.serverless.start({"handler": handler})
