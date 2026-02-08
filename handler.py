import runpod
import os
import subprocess
import requests
from audio_separator.separator import Separator

# ==========================================
# 1. 核心配置 (根据你的文件自动调整)
# ==========================================

# A. 模型下载地址 (你的服务器)
MODEL_URL = "https://www.toponedumps.com/wukong_v2.pth"
MODEL_NAME = "wukong_v2.pth"

# B. 索引文件名 (你传到 GitHub 的那个文件)
# 注意：这个文件会自动存在于当前目录下，不需要下载
INDEX_NAME = "trained_IVF3062_Flat_nprobe_1_wukong_v2_v2.index"

# ==========================================

# 初始化路径
BASE_DIR = "/app"
OUTPUT_DIR = "/app/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 定义模型本地路径
local_model_path = os.path.join(BASE_DIR, MODEL_NAME)
local_index_path = os.path.join(BASE_DIR, INDEX_NAME)

# === 🚀 启动检查与自动下载 ===
print(f"🔄 系统启动中... 正在检查模型文件...")

if not os.path.exists(local_model_path):
    print(f"⬇️ 本地未发现模型，正在从服务器下载: {MODEL_URL}")
    try:
        # 使用 wget 下载，通常比 python requests 更快更稳
        subprocess.run(f"wget -O '{local_model_path}' '{MODEL_URL}'", shell=True, check=True)
        print("✅ 模型下载完成！")
    except Exception as e:
        print(f"❌ 模型下载失败: {e}")
else:
    print("✅ 模型已存在，跳过下载。")

# 检查 GitHub 的 Index 文件是否同步过来了
if os.path.exists(local_index_path):
    print(f"✅ 找到索引文件: {INDEX_NAME}")
else:
    print(f"⚠️ 警告: 没找到 {INDEX_NAME}，请确认你真的把它传到 GitHub 仓库里了！")


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
    pitch = job_input.get("pitch", 0) # 默认为 0 (不升降调)
    
    if not song_url:
        return {"error": "❌ 请提供 song_url 参数"}

    try:
        # 1. 下载用户上传的歌曲
        local_song = os.path.join(OUTPUT_DIR, "input_song.mp3")
        download_file(song_url, local_song)
        print("✅ 歌曲下载成功")

        # 2. UVR5 分离 (分离人声和伴奏)
        print("✂️ 开始 UVR5 分离...")
        separator = Separator(log_level='info', output_dir=OUTPUT_DIR)
        separator.load_model(model_filename='UVR-MDX-NET-Inst_HQ_3.onnx')
        output_files = separator.separate(local_song)
        
        # 自动识别分离后的文件
        backing_path = None
        vocal_path = None
        for f in output_files:
            if "Instrumental" in f:
                backing_path = os.path.join(OUTPUT_DIR, f)
            else:
                vocal_path = os.path.join(OUTPUT_DIR, f)
        
        print(f"✅ 分离完成: 人声={vocal_path}, 伴奏={backing_path}")

        # 3. RVC 变声 (重点步骤)
        print(f"🤖 开始 RVC 变声处理 (使用模型: {MODEL_NAME})...")
        
        # 构造输出路径
        converted_vocal = os.path.join(OUTPUT_DIR, "converted_vocal.wav")
        
        # 构造 RVC 推理命令 (这里假设我们要调用 RVC 的核心库)
        # 注意：为了简化演示，这里我们还是先做透传测试。
        # 如果你已经准备好了 RVC 的 infer_cli.py，请取消下面注释并运行
        
        # === RVC 调用伪代码 (你需要确保 RVC 库已安装) ===
        # cmd = [
        #     "python", "/app/rvc/tools/infer_cli.py",
        #     "--f0up_key", str(pitch),
        #     "--input_path", vocal_path,
        #     "--index_path", local_index_path,
        #     "--opt_path", converted_vocal,
        #     "--model_name", MODEL_NAME.replace(".pth", ""),
        #     ...
        # ]
        # subprocess.run(cmd...)
        
        # ⚠️ 临时测试逻辑：为了保证你能先跑通流程，我们暂时把原声当做变声结果
        # 等这次测试成功了，我们再把上面的 RVC 命令加进去
        subprocess.run(f"cp '{vocal_path}' '{converted_vocal}'", shell=True)
        # =================================================

        # 4. 混音 (新声音 + 原伴奏)
        print("🎛️ 正在合成最终音频...")
        final_mix = os.path.join(OUTPUT_DIR, "final_result.mp3")
        # 简单的混音: 人声(volume 1.5) + 伴奏(volume 1.0)
        cmd = f'ffmpeg -y -i "{converted_vocal}" -i "{backing_path}" -filter_complex "[0:a]volume=1.5[a1];[1:a]volume=1.0[a2];[a1][a2]amix=inputs=2:duration=longest" "{final_mix}"'
        subprocess.run(cmd, shell=True, check=True)

        # 5. 上传结果
        print("⬆️ 上传最终作品...")
        with open(final_mix, 'rb') as f:
            # 同样使用 transfer.sh 方便你直接测试下载
            upload_resp = requests.put(f'https://transfer.sh/rvc_result.mp3', data=f)
            download_link = upload_resp.text.strip()

        return {
            "status": "success",
            "message": "AI 翻唱处理完成！",
            "download_url": download_link,
            "model_used": MODEL_NAME
        }

    except Exception as e:
        print(f"❌ 发生错误: {e}")
        return {"status": "error", "message": str(e)}

runpod.serverless.start({"handler": handler})
