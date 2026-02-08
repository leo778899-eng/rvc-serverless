# 1. 基础镜像
FROM runpod/pytorch:2.0.1-py3.10-cuda11.8.0-devel

# 2. 系统依赖 (确保 git 和 ninja 都在)
USER root
RUN apt-get update && \
    apt-get install -y ffmpeg build-essential gcc g++ ninja-build git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. 升级工具链
RUN pip install --upgrade pip setuptools wheel

# 4. 铺路：先安装 Cython 和 Numpy
# 这是最关键的一步，必须在安装 fairseq 之前存在
RUN pip install "numpy<2" "cython<3"

# 5. 【核心修复】手动下载源码并强制安装
# 使用 --no-build-isolation 参数，强制它使用上面装好的 numpy
RUN git clone https://github.com/facebookresearch/fairseq.git && \
    cd fairseq && \
    pip install --no-build-isolation . && \
    cd .. && \
    rm -rf fairseq

# 6. 复制剩余文件
COPY requirements.txt .
COPY handler.py .

# 7. 安装剩下的库 (requirements.txt 里千万别再写 fairseq 了)
RUN pip install -r requirements.txt

# 8. 启动
CMD [ "python", "-u", "/app/handler.py" ]
