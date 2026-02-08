# 1.【关键修改】更换为 PyTorch 1.13 镜像
# 这是 RVC 最喜欢的环境，fairseq 在这里可以免编译直接跑，或者编译极其顺畅
FROM runpod/pytorch:1.13.1-py3.10-cuda11.7.1-devel-ubuntu22.04

# 2. 系统依赖
USER root
RUN apt-get update && \
    apt-get install -y ffmpeg build-essential gcc g++ git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. 复制文件
COPY requirements.txt .
COPY handler.py .

# 4. 升级 pip
RUN pip install --upgrade pip setuptools wheel

# 5. 安装 Python 依赖
# 注意：在 PyTorch 1.13 环境下，fairseq 安装非常老实，不需要额外参数
# 我们先单独装 numpy 确保稳定
RUN pip install "numpy<1.24" 
RUN pip install -r requirements.txt

# 6. 启动
CMD [ "python", "-u", "/app/handler.py" ]
