# 1.【修正】使用存在的镜像标签 (PyTorch 1.13.0)
FROM runpod/pytorch:1.13.0-py3.10-cuda11.7.1-devel

# 2. 系统依赖 (增加 libsndfile1，这是处理音频必须的)
USER root
RUN apt-get update && \
    apt-get install -y ffmpeg build-essential gcc g++ git libsndfile1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. 复制文件
COPY requirements.txt .
COPY handler.py .

# 4. 升级 pip
RUN pip install --upgrade pip setuptools wheel

# 5. 安装 Python 依赖
# 在 PyTorch 1.13 + Python 3.10 环境下，fairseq 0.12.2 可以直接安装成功
# 我们先锁定 numpy 版本，防止冲突
RUN pip install "numpy<1.24"
RUN pip install -r requirements.txt

# 6. 启动
CMD [ "python", "-u", "/app/handler.py" ]
