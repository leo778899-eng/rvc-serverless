# 使用 RunPod 官方基础镜像
FROM runpod/pytorch:2.0.1-py3.10-cuda11.8.0-devel

# === 1. 安装系统级依赖 (增强版) ===
# 增加了 build-essential 和 gcc，防止 pip 安装失败
USER root
RUN apt-get update && \
    apt-get install -y ffmpeg build-essential python3-dev gcc g++ && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# === 2. 设置工作目录 ===
WORKDIR /app

# === 3. 复制依赖文件 ===
COPY requirements.txt .
COPY handler.py .

# === 4. 安装 Python 依赖 ===
# 使用 --no-cache-dir 减小体积，并先单独安装容易报错的 numpy
RUN pip install --upgrade pip && \
    pip install --no-cache-dir "numpy<2" && \
    pip install --no-cache-dir -r requirements.txt

# === 5. 设置启动命令 ===
CMD [ "python", "-u", "/app/handler.py" ]
