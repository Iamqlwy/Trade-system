"""
Docker 沙箱测试脚本。

运行: python test_sandbox.py
"""

import asyncio
import sys
from pathlib import Path


async def test_sandbox():
    """测试沙箱功能"""
    # 添加项目根目录到路径
    project_root = Path(__file__).parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from app.agent.tools.sandbox import SandboxManager, SandboxConfig

    # 创建测试工作区
    work_dir = project_root / "test_workspace"
    work_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("Docker 沙箱测试")
    print("=" * 60)

    # 创建配置
    config = SandboxConfig(
        work_dir=work_dir.resolve(),
        user_id=1,
        session_id="test_session_001",
        docker_enabled=True,
        block_network=True,
        max_memory_mb=256,
        max_cpus=0.5,
        max_pids=8,
    )

    # 创建沙箱管理器
    mgr = SandboxManager(config)
    print(f"\n后端: {mgr.backend_name}")
    print(f"已沙箱化: {mgr.is_sandboxed}")
    print("-" * 60)

    tests = [
        ("基本命令", "echo hello world", True, "hello world"),
        ("Python 版本", "python --version", True, "Python"),
        ("工作区写入", "echo 'test content' > /workspace/test.txt && cat /workspace/test.txt", True, "test content"),
        ("根文件系统只读", "touch /root_test.txt", False, None),
        ("/etc 只读", "touch /etc/test_file", False, None),
        ("网络不可用", "curl -s --connect-timeout 3 http://example.com", False, None),
        ("环境变量清洗", "env | sort", True, None),  # 后续检查敏感变量
        ("ls 工作区", "ls -la /workspace/", True, None),
    ]

    passed = 0
    failed = 0

    for name, cmd, should_succeed, expected_output in tests:
        print(f"\n[测试] {name}")
        print(f"  命令: {cmd}")

        try:
            result = await mgr.execute(cmd, timeout=30)

            if result.timed_out:
                print(f"  ⏱ 超时")
                if not should_succeed:
                    print(f"  ✓ 预期失败")
                    passed += 1
                else:
                    print(f"  ✗ 应该成功")
                    failed += 1
                continue

            success = result.exit_code == 0
            output = result.stdout.strip()

            print(f"  退出码: {result.exit_code}")
            if output:
                print(f"  输出: {output[:200]}")

            # 检查结果
            if name == "环境变量清洗":
                # 检查是否有敏感变量
                has_sensitive = any(
                    x in output.upper()
                    for x in ["DB_PASSWORD", "LLM_API_KEY", "JWT_SECRET", "OSS_ACCESS"]
                )
                if has_sensitive:
                    print(f"  ✗ 发现敏感环境变量!")
                    failed += 1
                else:
                    print(f"  ✓ 环境变量已清洗")
                    passed += 1
            elif should_succeed:
                if success:
                    if expected_output and expected_output not in output:
                        print(f"  ✗ 输出不包含期望内容: {expected_output}")
                        failed += 1
                    else:
                        print(f"  ✓ 成功")
                        passed += 1
                else:
                    print(f"  ✗ 应该成功但失败了: {result.stderr[:200]}")
                    failed += 1
            else:
                if not success:
                    print(f"  ✓ 预期失败")
                    passed += 1
                else:
                    print(f"  ✗ 应该失败但成功了")
                    failed += 1

        except Exception as e:
            print(f"  ✗ 异常: {e}")
            if not should_succeed:
                passed += 1
            else:
                failed += 1

    # 测试 Shell 工具集成
    print("\n" + "=" * 60)
    print("Shell 工具集成测试")
    print("=" * 60)

    from app.agent.tools.shell import Shell

    shell = Shell(work_dir=work_dir, user_id=1, session_id="test_shell")
    print(f"\nShell 沙箱后端: {shell._sandbox.backend_name}")

    result = await shell.call({"command": "echo 'Shell tool test'", "timeout": 10})
    print(f"结果: {result.get('message', '')}")
    if not result.get("is_error"):
        print(f"输出: {result.get('output', '')[:100]}")
        print("✓ Shell 工具集成正常")
        passed += 1
    else:
        print(f"✗ Shell 工具出错: {result.get('message', '')}")
        failed += 1

    # 总结
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    # 清理测试文件
    test_file = work_dir / "test.txt"
    if test_file.exists():
        test_file.unlink()
    if work_dir.exists() and not any(work_dir.iterdir()):
        work_dir.rmdir()

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(test_sandbox())
    sys.exit(0 if success else 1)
