# 1. 使用 RunPod 官方基础镜像
FROM runpod/pytorch:2.0.1-py3.10-cuda11.8.0-devel

# 2. 安装系统依赖 (增加了 ninja-build，防止 fairseq 偶尔抽风)
USER root
RUN apt-get update && \
    apt-get install -y ffmpeg build-essential gcc g++ ninja-build && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. 复制文件
COPY requirements.txt .
COPY handler.py .

# 4. 升级 pip
RUN pip install --upgrade pip setuptools wheel

# 5. 安装核心依赖 (锁定 numpy 版本，防止冲突)
RUN pip install "numpy<2" "cython<3"

# 6. 安装 Fairseq (直接从 PyPI 安装 0.12.2 稳定版，不要用 git 了！)
RUN pip install fairseq==0.12.2

# 7. 安装剩下的库
RUN pip install -r requirements.txt

# 8. 启动
CMD [ "python", "-u", "/app/handler.py" ]
