# 1. 基础镜像 (PyTorch 1.13.0, RVC 的完美底座)
FROM runpod/pytorch:1.13.0-py3.10-cuda11.7.1-devel

# 2. 系统依赖 (关键：增加了 llvm-dev，这是安装 llvmlite/numba 必须的)
USER root
RUN apt-get update && \
    apt-get install -y ffmpeg build-essential gcc g++ git libsndfile1 llvm-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. 复制文件
COPY requirements.txt .
COPY handler.py .

# 4. 升级 pip
RUN pip install --upgrade pip setuptools wheel

# 5. 【第一层地基】安装 Numpy 和 Cython
# 必须先装好它们，后面的 fairseq 才能编译
RUN pip install "numpy==1.23.5" "Cython<3"

# 6. 【第二层地基】安装 Fairseq
# 使用 --no-deps 防止它自动拉取不兼容的 numpy
RUN pip install --no-deps fairseq==0.12.2

# 7. 【第三层装修】安装剩余依赖
# 这一步会安装 audio-separator 等现代库
RUN pip install -r requirements.txt

# 8. 启动
CMD [ "python", "-u", "/app/handler.py" ]
