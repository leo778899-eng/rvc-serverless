# 1. 基础镜像
FROM runpod/pytorch:2.0.1-py3.10-cuda11.8.0-devel

# 2. 安装系统依赖 (保留 ninja 和编译器)
USER root
RUN apt-get update && \
    apt-get install -y ffmpeg build-essential gcc g++ ninja-build && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. 复制文件
COPY requirements.txt .
COPY handler.py .

# ========================================================
# 🛑 核心修复区：时光倒流 🛑
# fairseq 0.12.2 必须要用旧版的 setuptools 和 Cython 才能编译成功
# ========================================================

# 4. 强制降级构建工具 (这是最关键的一步！)
# setuptools<60: 恢复旧版打包功能
# Cython<3: 恢复旧版编译语法
# numpy<2: 恢复旧版数学库
RUN pip install --upgrade pip && \
    pip install "setuptools<60.0.0" "Cython<3.0.0" "numpy<2.0.0" wheel

# 5. 安装 Fairseq
# --no-build-isolation: 告诉 pip "用我刚才降级好的旧工具来编译"，不要自己去下新的
RUN pip install --no-build-isolation fairseq==0.12.2

# ========================================================

# 6. 安装剩下的库 (requirements.txt 里不要有 fairseq 和 numpy)
RUN pip install -r requirements.txt

# 7. 启动
CMD [ "python", "-u", "/app/handler.py" ]
