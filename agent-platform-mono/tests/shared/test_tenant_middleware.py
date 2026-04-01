"""
Tests for Task 1.1 - Context Model Extension
测试新增的 6 个上下文字段和 Authorization Bearer 解析
"""
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
from shared.middleware.tenant import (
    TenantContextMiddleware,
    get_current_user_id,
    get_current_auth_token,
    get_current_channel_id,
    get_current_tenant_type,
    get_current_locale,
    get_current_timezone,
    set_current_user_id,
    set_current_locale,
)


@pytest.fixture
def app():
    """创建测试应用"""
    app = Starlette()
    app.add_middleware(TenantContextMiddleware)
    
    @app.route("/test")
    async def test_endpoint(request):
        return JSONResponse({
            "user_id": get_current_user_id(),
            "auth_token": get_current_auth_token(),
            "channel_id": get_current_channel_id(),
            "tenant_type": get_current_tenant_type(),
            "locale": get_current_locale(),
            "timezone": get_current_timezone(),
        })
    
    return app


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return TestClient(app)


def test_new_context_fields_injection(client):
    """测试新增字段的注入和读取"""
    response = client.get("/test", headers={
        "X-User-Id": "user123",
        "X-Channel-Id": "channel456",
        "X-Tenant-Type": "enterprise",
        "X-Locale": "en-US",
        "X-Timezone": "America/New_York",
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "user123"
    assert data["channel_id"] == "channel456"
    assert data["tenant_type"] == "enterprise"
    assert data["locale"] == "en-US"
    assert data["timezone"] == "America/New_York"


def test_authorization_bearer_parsing(client):
    """测试 Authorization: Bearer {token} 解析"""
    response = client.get("/test", headers={
        "Authorization": "Bearer test_token_12345",
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["auth_token"] == "test_token_12345"


def test_authorization_bearer_invalid_format(client):
    """测试 Authorization 格式错误时的容错"""
    # 不是 Bearer 格式
    response = client.get("/test", headers={
        "Authorization": "Basic dXNlcjpwYXNz",
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["auth_token"] == ""  # 解析失败返回空字符串
    
    # 空 Authorization
    response = client.get("/test", headers={
        "Authorization": "",
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["auth_token"] == ""


def test_missing_headers_default_values(client):
    """测试缺失 header 时的默认值"""
    response = client.get("/test")
    
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == ""
    assert data["auth_token"] == ""
    assert data["channel_id"] == ""
    assert data["tenant_type"] == ""
    assert data["locale"] == "zh-CN"  # 默认值
    assert data["timezone"] == "Asia/Shanghai"  # 默认值


def test_setter_functions():
    """测试 setter 函数"""
    set_current_user_id("new_user")
    assert get_current_user_id() == "new_user"
    
    set_current_locale("ja-JP")
    assert get_current_locale() == "ja-JP"


def test_authorization_bearer_with_extra_spaces(client):
    """测试 Bearer token 前后有空格的情况"""
    response = client.get("/test", headers={
        "Authorization": "Bearer   token_with_spaces   ",
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["auth_token"] == "token_with_spaces"  # strip() 应该去除空格


def test_all_fields_together(client):
    """测试所有新增字段同时传入"""
    response = client.get("/test", headers={
        "X-User-Id": "user_full",
        "Authorization": "Bearer full_token",
        "X-Channel-Id": "channel_full",
        "X-Tenant-Type": "individual",
        "X-Locale": "ja-JP",
        "X-Timezone": "Asia/Tokyo",
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "user_full"
    assert data["auth_token"] == "full_token"
    assert data["channel_id"] == "channel_full"
    assert data["tenant_type"] == "individual"
    assert data["locale"] == "ja-JP"
    assert data["timezone"] == "Asia/Tokyo"
