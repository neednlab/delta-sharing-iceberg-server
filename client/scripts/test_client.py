"""
Delta Sharing Iceberg 客户端测试脚本

该模块提供用于测试 Delta Sharing Server 连接和 Iceberg 表读取的功能。
支持 pandas 和 spark 两种模式读取共享表数据。

示例用法:
    # 列出所有可用表
    list_tables()

    # 使用 Spark 模式读取表
    read_table("my_share", "my_schema", "my_table", mode="spark")

    # 使用 Pandas 模式读取表
    read_table("my_share", "my_schema", "my_table", mode="pandas")
"""

import logging
import os
import sys

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "local.share")

script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
tmp_dir = os.path.join(script_dir, "tmp")
os.makedirs(tmp_dir, exist_ok=True)

import tempfile

tempfile.tempdir = tmp_dir


class SparkErrorFilter(logging.Filter):
    """日志过滤器，用于过滤 PySpark 产生的无关错误信息。

    某些 Spark 临时目录删除错误不影响实际功能，该过滤器
    会屏蔽这类常见的无害错误，避免干扰测试输出。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """判断日志记录是否应该被过滤。

        Args:
            record: 日志记录对象。

        Returns:
            如果记录应该被输出则返回 True，否则返回 False。
        """
        if record.levelno == logging.ERROR:
            msg = record.getMessage()
            if "Failed to delete" in msg and "spark" in msg.lower():
                return False
            if "Exception while deleting Spark temp dir" in msg:
                return False
        return True


spark_error_handler = logging.StreamHandler(sys.stderr)
spark_error_handler.setLevel(logging.ERROR)
spark_error_handler.addFilter(SparkErrorFilter())

logging.getLogger("py4j").addHandler(spark_error_handler)
logging.getLogger("py4j").setLevel(logging.ERROR)
logging.getLogger("pyspark").addHandler(spark_error_handler)
logging.getLogger("pyspark").setLevel(logging.ERROR)


def to_spark_path(path: str) -> str:
    """将 Windows 路径转换为有效的 Spark URI 格式。

    Spark 需要特定格式的路径，本函数将 Windows 风格的路劲
    (如 C:\\path\\to\\file) 转换为 Spark 能识别的 URI 格式。

    Args:
        path: 原 Windows 文件路径。

    Returns:
        转换后的 Spark URI 格式路径。
    """
    import re

    path = path.replace("\\", "/")
    if not re.match(r"^[a-zA-Z]:", path):
        path = "/" + path
    return f"file:///{path}"


def list_tables() -> list:
    """列出所有可用的 Delta Sharing 共享表。

    使用 delta-sharing 客户端连接服务器并列出所有共享表信息。

    Returns:
        包含所有表信息的列表，每个表对象包含 share、schema 和 name 属性。

    Raises:
        Exception: 连接服务器或获取列表失败时抛出异常。
    """
    import delta_sharing

    client = delta_sharing.SharingClient(CONFIG_PATH)
    tables = client.list_all_tables()
    print("Available tables:")
    for table in tables:
        print(f"  - Share: {table.share}, Schema: {table.schema}, Table: {table.name}")
    return tables


def read_table(share_name: str, schema_name: str, table_name: str, mode: str = "spark") -> None:
    """读取 Delta Sharing 共享表数据。

    支持使用 pandas 或 spark 两种模式读取 Iceberg 表数据。
    pandas 模式适合小数据量快速预览，spark 模式适合大规模数据分析。

    Args:
        share_name: 共享名称 (share)。
        schema_name: schema 名称。
        table_name: 表名称。
        mode: 读取模式，可选值为 "pandas" 或 "spark"，默认为 "spark"。

    Raises:
        Exception: 读取失败时抛出异常。
    """
    import time

    profile_uri = to_spark_path(CONFIG_PATH)
    url = f"{profile_uri}#{share_name}.{schema_name}.{table_name}"
    print(f"\nLoading: {url}")

    if mode == "pandas":
        import delta_sharing

        try:
            start_time = time.perf_counter()
            df = delta_sharing.load_as_pandas(url)
            end_time = time.perf_counter()
            elapsed_s = end_time - start_time
            print(f"\nQuery finished in {elapsed_s:.2f} s")
            print("\nData preview (first 10 rows):")
            print(df.head(10))
        except Exception as e:
            print(f"\nError: {e}")

    elif mode == "spark":
        import gc
        import shutil
        from pathlib import Path
        from pyspark.sql import SparkSession

        spark_tmp_dir = os.path.join(tmp_dir, "spark")
        os.makedirs(spark_tmp_dir, exist_ok=True)

        hadoop_home = os.path.join(script_dir, "hadoop-winutils")
        bin_dir = os.path.join(hadoop_home, "bin")
        os.makedirs(bin_dir, exist_ok=True)

        winutils_path = os.path.join(bin_dir, "winutils.exe")
        if not os.path.exists(winutils_path):
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

        log4j_props = """
         log4j.rootLogger=OFF, console
         log4j.appender.console=org.apache.log4j.ConsoleAppender
         log4j.appender.console.target=System.err
         log4j.appender.console.layout=org.apache.log4j.PatternLayout
         log4j.appender.console.layout.ConversionPattern=%d{yy/MM/dd HH:mm:ss} %p %c{1}: %m%n
         log4j.logger.org.apache.spark.repl.Main=OFF
         log4j.logger.org.apache.spark.SparkEnv=OFF
         log4j.logger.org.apache.spark.SparkContext=OFF
         log4j.logger.org.apache.spark.util.ShutdownHookManager=OFF
         log4j.logger.org.apache.hadoop.util.Shell=OFF
         log4j.logger.org.apache.hadoop.hdfs=OFF
         log4j.logger.org.apache.hadoop.util.NativeCodeLoader=OFF
         log4j.logger.org.apache.http=OFF
         log4j.logger.org=OFF
         """

        log4j_file = os.path.join(tmp_dir, "log4j.properties")
        with open(log4j_file, "w") as f:
            f.write(log4j_props)

        from pyspark import SparkConf

        # 使用本地预下载的 JAR 文件，避免每次启动时进行 Maven/Ivy 网络解析
        jars_dir = os.path.join(script_dir, "jars")
        if not os.path.isdir(jars_dir) or not any(f.endswith(".jar") for f in os.listdir(jars_dir)):
            print("[WARN] JAR 缓存目录为空，请先运行: uv run .\\scripts\\download_jars.py")
            print("[WARN] 回退到在线 Maven 解析模式...")
            packages_conf = ("spark.jars.packages", "io.delta:delta-sharing-spark_2.12:3.3.2")
        else:
            # 收集所有本地 JAR 文件路径，逗号分隔传给 spark.jars
            jar_files = sorted(
                os.path.join(jars_dir, f) for f in os.listdir(jars_dir) if f.endswith(".jar")
            )
            packages_conf = ("spark.jars", ",".join(jar_files))

        conf = SparkConf()
        conf.setMaster("local[*]")
        conf.setAppName("DeltaSharingDemo")
        conf.set(*packages_conf)
        conf.set(
            "spark.driver.extraJavaOptions",
            f"-Dlog4j.configuration=file:///{log4j_file.replace(chr(92), '/')}",
        )
        conf.set("spark.shutdownHookManager.enabled", "false")
        conf.set("spark.sql.parquet.enableVectorizedReader", "false")

        spark = SparkSession.builder.config(conf=conf).getOrCreate()

        try:
            start_time = time.perf_counter()

            
            sql = f"""
            CREATE TABLE needn_t1 USING deltaSharing
            LOCATION '{profile_uri}#{share_name}.{schema_name}.{table_name}'
            """
            spark.sql(sql)

            sql = """
            SELECT * FROM needn_t1
            --WHERE month_id = 202604
            LIMIT 20
            """
            spark.sql(sql).show()
            
            '''
            df_version = (
                spark.read.format("deltaSharing")
                .option("versionAsOf", 2)
                .load(f"{profile_uri}#{share_name}.{schema_name}.{table_name}")
            )

            df_version.show()
            '''

            end_time = time.perf_counter()
            elapsed_s = end_time - start_time
            print(f"Query finished in {elapsed_s:.2f} s")
        finally:
            try:
                spark.stop()
            except Exception:
                pass
            gc.collect()
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        print("Invalid mode. Choose 'pandas' or 'spark'.")


if __name__ == "__main__":
    list_tables()

    share_name = "needn_share"
    schema_name = "shared_cnslk"
    table_name = "dlc_t2"

    read_table(share_name, schema_name, table_name, mode="spark")
