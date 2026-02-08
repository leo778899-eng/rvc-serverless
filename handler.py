import runpod
import os
import subprocess
import requests
import logging
import shutil # <--- 新增：用来暴力删除文件夹
from audio_separator.separator import Separator

# ==========================================
# 🛑 1. 暴力环境修复 (依赖包)
# ==========================================
print("🚑 正在检查基础环境依赖...")
try:
    # 强制安装 av (解决上一轮报错), fairseq, faiss-cpu, numpy
    subprocess.run("pip install av fairseq faiss-cpu numpy --upgrade --no-cache-dir", shell=True, check=True)
    print("✅ 依赖修复完成！")
except Exception as e:
    print(f"⚠️ 依赖安装遇到小问题: {e}")

# ==========================================
# 2. 核心配置
# ==========================================
MODEL_URL = "https://www.toponedumps.com/wukong_v2.pth"
MODEL_NAME = "wukong_v2.pth" 
INDEX_NAME = "trained_IVF3062_Flat_nprobe_1_wukong_v2_v2.index"

# RVC 配置
RVC_GIT_URL = "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git"
RVC_DIR = "/app/RVC_Code"  
WEIGHTS_DIR = os.path.join(RVC_DIR, "weights")

# 关键脚本位置
RVC_INFER_SCRIPT = os.path.join(RVC_DIR, "tools", "infer_cli.py")

# ==========================================

BASE_DIR = "/app"
OUTPUT_DIR = "/app/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(WEIGHTS_DIR, exist_ok=True)

# ==========================================
# 🛑 3. 智能代码下载 (防坑逻辑)
# ==========================================
# 只有当核心文件真的存在时，才算下载成功
if not os.path.exists(RVC_INFER_SCRIPT):
    print("🚀 未检测到完整的 RVC 代码，准备下载...")
    
    # 如果文件夹存在但文件不在，说明是坏的，删掉重来！
    if os.path.exists(RVC_DIR):
        print(f"🧹 检测到残留文件夹 {RVC_DIR}，正在清理...")
        shutil.rmtree(RVC_DIR)
        print("✅ 清理完毕。")

    try:
        print(f"⬇️ 正在从 GitHub 克隆到 {RVC_DIR} ...")
        subprocess.run(f"git clone {RVC_GIT_URL} {RVC_DIR}", shell=True, check=True)
        print("✅ RVC 代码下载完成！")
        
        # 再次确认依赖
        if os.path.exists(os.path.join(RVC_DIR, "requirements.txt")):
             print("📦 安装 RVC 内部依赖...")
             subprocess.run(f"pip install -r {RVC_DIR}/requirements.txt", shell=True)
    except Exception as e:
        print(f"❌ RVC 代码下载失败: {e}")
        # 如果下载失败，抛出异常，不要继续跑了
        raise Exception("RVC代码下载失败，无法继续")
else:
    print("✅ RVC 代码完整，跳过下载。")

# ==========================================

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
        
        # 如果没分离出人声（比如是纯音乐），做个兜底
        if not vocal_path:
             raise Exception("未检测到人声，请换一首歌测试")
             
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
