"""
Delta Sharing Spark JAR 依赖预下载脚本

本脚本通过启动一个最小化的 SparkSession 来触发 Maven/Ivy 依赖解析，
将所有需要的 JAR 文件下载到本地持久化缓存目录 client/jars/。

运行一次后，test_client.py 将直接使用本地 JAR 文件，无需每次
启动时进行 Maven 坐标解析和网络检查，显著加快客户端启动速度。

用法:
    cd client
    uv run .\\scripts\\download_jars.py
"""

import os
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
JARS_DIR = os.path.join(CLIENT_DIR, "jars")
CACHE_DIR = os.path.join(CLIENT_DIR, ".cache", "ivy2")

# 需要下载的 Maven 依赖包
# delta-sharing-spark 3.3.2 内置 delta-sharing-client 1.2.2，支持 jsonPredicateHints 传输非分区列谓词
PACKAGES = "io.delta:delta-sharing-spark_2.12:3.3.2"


def download_jars():
    """使用 PySpark 触发依赖下载，并将 JAR 复制到本地缓存目录。"""
    print(f"[INFO] JAR 目标目录: {JARS_DIR}")
    print(f"[INFO] Ivy 缓存目录: {CACHE_DIR}")
    print(f"[INFO] 解析依赖包: {PACKAGES}")

    # 清理可能存在的旧缓存（可选，首次运行时可注释掉以强制重新下载）
    # if os.path.exists(CACHE_DIR):
    #     shutil.rmtree(CACHE_DIR)

    os.makedirs(JARS_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    # 配置临时目录（仅用于 Ivy 缓存和日志，不覆盖 JVM/Spark 默认 temp 路径）
    tmp_dir = os.path.join(CLIENT_DIR, "tmp")
    spark_tmp_dir = os.path.join(tmp_dir, "spark")
    os.makedirs(spark_tmp_dir, exist_ok=True)

    # 配置 Hadoop 环境（Windows 兼容性）
    hadoop_home = os.path.join(CLIENT_DIR, "hadoop-winutils")
    bin_dir = os.path.join(hadoop_home, "bin")
    os.makedirs(bin_dir, exist_ok=True)

    winutils_path = os.path.join(bin_dir, "winutils.exe")
    if not os.path.exists(winutils_path):
        from pathlib import Path

        winutils_source = (
            os.path.join(os.environ.get("HADOOP_HOME", ""), "bin", "winutils.exe")
            if os.environ.get("HADOOP_HOME")
            else None
        )
        if winutils_source and os.path.exists(winutils_source):
            shutil.copy(winutils_source, winutils_path)
        else:
            Path(winutils_path).touch()

    os.environ["HADOOP_HOME"] = hadoop_home
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

    print("[INFO] 启动 SparkSession 触发依赖下载...")

    from pyspark import SparkConf
    from pyspark.sql import SparkSession

    conf = SparkConf()
    conf.setMaster("local[1]")
    conf.setAppName("DeltaSharingJarDownloader")
    conf.set("spark.jars.packages", PACKAGES)
    conf.set("spark.jars.ivy", CACHE_DIR)
    conf.set(
        "spark.sql.catalog.spark_catalog",
        "org.apache.spark.sql.execution.datasources.v2.V2SessionCatalog",
    )
    conf.set("spark.driver.memory", "512m")

    try:
        spark = SparkSession.builder.config(conf=conf).getOrCreate()
        print("[INFO] SparkSession 创建成功，依赖已解析到 Ivy 缓存")
        spark.stop()
        print("[INFO] SparkSession 已停止")
    except Exception as e:
        print(f"[WARN] SparkSession 启动出现异常（可能 JAR 已下载）: {e}")

    # 收集所有下载的 JAR 文件（仅从 Ivy 解析后的 jars 目录复制，避免缓存目录中的重复）
    print("[INFO] 正在从 Ivy 缓存收集 JAR 文件...")
    ivy_jars_dir = os.path.join(CACHE_DIR, "jars")
    jar_count = 0
    if os.path.isdir(ivy_jars_dir):
        for f in os.listdir(ivy_jars_dir):
            if f.endswith(".jar"):
                src = os.path.join(ivy_jars_dir, f)
                dst = os.path.join(JARS_DIR, f)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    jar_count += 1
                    print(f"  [COPY] {f}")
    else:
        # 如果 jars 目录不存在，回退到遍历整个缓存目录
        for root, dirs, files in os.walk(CACHE_DIR):
            # 跳过 cache/ 子目录（其中存放的是带 groupId 前缀的原始包，jars/ 中已有解析后的版本）
            dirs[:] = [d for d in dirs if d != "cache" or root != CACHE_DIR]
            for f in files:
                if f.endswith(".jar"):
                    src = os.path.join(root, f)
                    dst = os.path.join(JARS_DIR, f)
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)
                        jar_count += 1
                        print(f"  [COPY] {f}")

    print(f"\n[DONE] 共复制 {jar_count} 个 JAR 文件到 {JARS_DIR}")

    # 列出最终缓存中的 JAR 文件
    final_jars = [f for f in os.listdir(JARS_DIR) if f.endswith(".jar")]
    print(f"[INFO] JAR 缓存目录现有 {len(final_jars)} 个文件:")
    for jar in sorted(final_jars):
        size_mb = os.path.getsize(os.path.join(JARS_DIR, jar)) / (1024 * 1024)
        print(f"  - {jar} ({size_mb:.2f} MB)")

    # 清理临时目录
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 清理 Ivy 缓存元数据（保留 jars 目录即可）
    # 如果不需要保留 Ivy 缓存可以取消注释下一行
    # shutil.rmtree(CACHE_DIR, ignore_errors=True)

    print("[INFO] 预下载完成！现在运行 test_client.py 将直接使用本地 JAR 文件。")


if __name__ == "__main__":
    download_jars()
