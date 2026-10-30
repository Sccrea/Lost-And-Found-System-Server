"""直接启动失物招领服务端。

用法（在本仓库根目录）：python run_server.py

证书、端口、DEBUG 均来自 config.json：
- SSL_CERT_FILE / SSL_KEY_FILE：HTTPS 证书与私钥，相对路径按本文件所在目录解析
- SERVER_HOST / SERVER_PORT：监听地址（需与内网穿透的 localPort 一致）
"""

import server


def main():
    try:
        server.main()
    except (FileNotFoundError, RuntimeError, OSError) as error:
        print(f"[启动失败] {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
