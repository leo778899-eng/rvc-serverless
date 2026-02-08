# 使用 RunPod 官方基础镜像 (带 CUDA 11.8 和 Python 3.10)
FROM runpod/pytorch:2.0.1-py3.10-cuda11.8.0-devel

# 1. 安装系统级依赖 (FFmpeg 是处理音频必须的)
USER root
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 2. 设置工作目录
WORKDIR /app

# 3. 复制项目文件到容器里
COPY requirements.txt .
COPY handler.py .

# 4. 安装 Python 依赖
# 注意：这里先升级 pip，然后安装依赖
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 5. 设置启动命令
CMD [ "python", "-u", "/app/handler.py" ]
