# 使用官方基础镜像
FROM runpod/pytorch:2.0.1-py3.10-cuda11.8.0-devel

# 1. 安装系统级依赖 (补充了 LLVM，防止 llvmlite 报错)
USER root
RUN apt-get update && \
    apt-get install -y ffmpeg build-essential git gcc g++ && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. 复制文件
COPY requirements.txt .
COPY handler.py .

# 3. 升级基础工具 (先把造房子的工具修好)
RUN pip install --upgrade pip setuptools wheel

# 4. 单独安装核心编译环境 (关键！很多库安装失败就是因为缺 Cython)
# 强制安装旧版 Numpy 防止版本冲突
RUN pip install "numpy<2" "cython<3"

# 5. 单独安装 Fairseq (最容易报错的库，我们单独处理)
# 使用 --no-build-isolation 确保它能用到上面安装好的 numpy
RUN pip install --no-build-isolation git+https://github.com/facebookresearch/fairseq.git

# 6. 安装剩下的库
RUN pip install -r requirements.txt

# 7. 启动
CMD [ "python", "-u", "/app/handler.py" ]
