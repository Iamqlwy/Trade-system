"""
最小化诊断脚本 —— 证明 /api/auth/me 在 DB 无用户时的实际行为。
直接运行: python test_auth_flow.py
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# 确保 JWT_SECRET 存在
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-diagnosis")

from unittest.mock import MagicMock, patch

# === Step 1: 验证 JWT 生成 ===
from app.auth.security import create_token, decode_token
token = create_token(user_id=999, username="ghost", role="admin")
payload = decode_token(token)
print(f"[Step 1] JWT 生成/解码: payload={payload}")
assert payload is not None, "JWT 解码失败！"
assert payload["user_id"] == 999

# === Step 2: 模拟 DB 为空，调用 /api/auth/me ===
fake_session = MagicMock()
fake_session.query.return_value.filter_by.return_value.first.return_value = None

with patch("app.api.auth_api.repository.SessionLocal", return_value=fake_session):
    from app.main import app
    from starlette.testclient import TestClient
    client = TestClient(app)

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    print(f"\n[Step 2] GET /api/auth/me (DB 空, 有效 token)")
    print(f"  status_code = {resp.status_code}")
    print(f"  body        = {resp.json()}")

    if resp.status_code == 401:
        print("  ✅ 结论: 后端正确返回 401")
    else:
        print(f"  ❌ 结论: 后端返回 {resp.status_code} 而非 401！这就是 BUG 所在！")

# === Step 3: 验证中间件是否正确拦截无效 token ===
with patch("app.api.auth_api.repository.SessionLocal", return_value=fake_session):
    resp2 = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
    print(f"\n[Step 3] GET /api/auth/me (无效 token)")
    print(f"  status_code = {resp2.status_code}")
    print(f"  body        = {resp2.json()}")

# === Step 4: 验证无 token 时的行为 ===
with patch("app.api.auth_api.repository.SessionLocal", return_value=fake_session):
    resp3 = client.get("/api/auth/me")
    print(f"\n[Step 4] GET /api/auth/me (无 token)")
    print(f"  status_code = {resp3.status_code}")
    print(f"  body        = {resp3.json()}")

print("\n" + "=" * 60)
print("如果 Step 2 返回 401，则后端无 bug。")
print("问题在前端：请在浏览器 DevTools → Network 中查看")
print("刷新页面时 /api/auth/me 的实际响应码。")
print("=" * 60)
