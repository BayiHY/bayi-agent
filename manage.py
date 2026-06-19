#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bayi-Agent 服务管理命令

提供启动、停止、重启服务的管理功能，并通知飞书
"""
import os
import sys
import subprocess
import argparse
import json
import time
from pathlib import Path
from datetime import datetime

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_feishu_config():
    """加载飞书配置"""
    import yaml
    config_path = os.environ.get("BAYI_CONFIG", os.path.join(os.path.dirname(__file__), "bayi_config.yaml"))
    
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config.get("feishu", {})
    
    return {}


def send_feishu_notification(message: str, title: str = "Bayi-Agent 服务通知"):
    """
    发送飞书通知
    
    Args:
        message: 消息内容
        title: 消息标题
    """
    try:
        import aiohttp
        import asyncio
        
        feishu_config = load_feishu_config()
        app_id = feishu_config.get("app_id", "")
        
        # 使用飞书机器人发送消息
        # 这里简化为日志输出，实际需要调用飞书 API
        print(f"\n{'='*60}")
        print(f"📢 {title}")
        print(f"{'='*60}")
        print(f"{message}")
        print(f"{'='*60}\n")
        
        # 如果有 webhook URL，发送通知
        webhook_url = feishu_config.get("webhook_url")
        if webhook_url:
            async def send_webhook():
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "msg_type": "text",
                        "content": {
                            "text": f"{title}\n{message}"
                        }
                    }
                    async with session.post(webhook_url, json=payload) as resp:
                        if resp.status == 200:
                            print("✅ 飞书通知发送成功")
                        else:
                            print(f"⚠️ 飞书通知发送失败: {resp.status}")
            
            asyncio.run(send_webhook())
        
    except Exception as e:
        print(f"⚠️ 发送飞书通知失败: {e}")


def check_service_status():
    """检查服务状态"""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "bayi-agent"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.stdout.strip() == "active"
    except Exception as e:
        print(f"⚠️ 检查服务状态失败: {e}")
        return False


def start_service():
    """启动服务"""
    print("🚀 启动 Bayi-Agent 服务...")
    
    if check_service_status():
        print("⚠️ 服务已在运行中")
        send_feishu_notification(
            "Bayi-Agent 服务已在运行中，无需重复启动",
            "⚠️ 服务状态提醒"
        )
        return False
    
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "start", "bayi-agent"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            time.sleep(2)  # 等待服务启动
            
            if check_service_status():
                print("✅ 服务启动成功")
                send_feishu_notification(
                    f"Bayi-Agent 服务已成功启动\n启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "✅ 服务启动成功"
                )
                return True
            else:
                print("❌ 服务启动失败")
                send_feishu_notification(
                    "Bayi-Agent 服务启动失败，请检查日志",
                    "❌ 服务启动失败"
                )
                return False
        else:
            print(f"❌ 启动命令执行失败: {result.stderr}")
            send_feishu_notification(
                f"Bayi-Agent 启动命令执行失败\n错误: {result.stderr}",
                "❌ 服务启动失败"
            )
            return False
            
    except Exception as e:
        print(f"❌ 启动服务异常: {e}")
        send_feishu_notification(
            f"Bayi-Agent 启动服务异常\n错误: {e}",
            "❌ 服务启动异常"
        )
        return False


def stop_service():
    """停止服务"""
    print("🛑 停止 Bayi-Agent 服务...")
    
    if not check_service_status():
        print("⚠️ 服务未在运行")
        send_feishu_notification(
            "Bayi-Agent 服务未在运行，无需停止",
            "⚠️ 服务状态提醒"
        )
        return False
    
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "stop", "bayi-agent"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            time.sleep(1)  # 等待服务停止
            
            if not check_service_status():
                print("✅ 服务停止成功")
                send_feishu_notification(
                    f"Bayi-Agent 服务已成功停止\n停止时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "✅ 服务停止成功"
                )
                return True
            else:
                print("❌ 服务停止失败")
                send_feishu_notification(
                    "Bayi-Agent 服务停止失败，请检查日志",
                    "❌ 服务停止失败"
                )
                return False
        else:
            print(f"❌ 停止命令执行失败: {result.stderr}")
            send_feishu_notification(
                f"Bayi-Agent 停止命令执行失败\n错误: {result.stderr}",
                "❌ 服务停止失败"
            )
            return False
            
    except Exception as e:
        print(f"❌ 停止服务异常: {e}")
        send_feishu_notification(
            f"Bayi-Agent 停止服务异常\n错误: {e}",
            "❌ 服务停止异常"
        )
        return False


def restart_service():
    """重启服务"""
    print("🔄 重启 Bayi-Agent 服务...")
    
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "bayi-agent"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            time.sleep(2)  # 等待服务重启
            
            if check_service_status():
                print("✅ 服务重启成功")
                send_feishu_notification(
                    f"Bayi-Agent 服务已成功重启\n重启时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "✅ 服务重启成功"
                )
                return True
            else:
                print("❌ 服务重启失败")
                send_feishu_notification(
                    "Bayi-Agent 服务重启失败，请检查日志",
                    "❌ 服务重启失败"
                )
                return False
        else:
            print(f"❌ 重启命令执行失败: {result.stderr}")
            send_feishu_notification(
                f"Bayi-Agent 重启命令执行失败\n错误: {result.stderr}",
                "❌ 服务重启失败"
            )
            return False
            
    except Exception as e:
        print(f"❌ 重启服务异常: {e}")
        send_feishu_notification(
            f"Bayi-Agent 重启服务异常\n错误: {e}",
            "❌ 服务重启异常"
        )
        return False


def status_service():
    """查看服务状态"""
    try:
        result = subprocess.run(
            ["systemctl", "status", "bayi-agent"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        print(result.stdout)
        
        # 解析状态
        is_active = "active (running)" in result.stdout
        status_text = "运行中" if is_active else "已停止"
        
        send_feishu_notification(
            f"Bayi-Agent 服务状态: {status_text}\n查看时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"📊 服务状态: {status_text}"
        )
        
        return is_active
        
    except Exception as e:
        print(f"❌ 查看状态失败: {e}")
        return False


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="Bayi-Agent 服务管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python manage.py start      # 启动服务
  python manage.py stop       # 停止服务
  python manage.py restart    # 重启服务
  python manage.py status     # 查看状态
        """
    )
    
    parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "status"],
        help="执行的操作"
    )
    
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="不发送飞书通知"
    )
    
    args = parser.parse_args()
    
    # 执行操作
    if args.action == "start":
        start_service()
    elif args.action == "stop":
        stop_service()
    elif args.action == "restart":
        restart_service()
    elif args.action == "status":
        status_service()


if __name__ == "__main__":
    main()
