# -*- coding: utf-8 -*-
"""Simple authentication module for CoPaw console.

This module provides a basic login protection for the CoPaw console when
deployed on a public server. It uses session-based authentication with
hardcoded credentials that can be overridden via environment variables.
"""
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Default credentials (hardcoded, can be overridden via env vars)
# These are randomly generated complex credentials
DEFAULT_USERNAME = "copaw_admin"
DEFAULT_PASSWORD = "Xk9#mP2$vL7@nQ4wR8tY"


@dataclass
class AuthConfig:
    """Authentication configuration."""

    enabled: bool = True
    username: str = DEFAULT_USERNAME
    password: str = DEFAULT_PASSWORD
    session_expire_hours: int = 24

    def __post_init__(self) -> None:
        """Load configuration from environment variables."""
        env_enabled = os.environ.get("COPAW_AUTH_ENABLED", "").lower()
        if env_enabled in ("false", "0", "no"):
            self.enabled = False
        elif env_enabled in ("true", "1", "yes"):
            self.enabled = True

        env_username = os.environ.get("COPAW_AUTH_USERNAME")
        if env_username:
            self.username = env_username

        env_password = os.environ.get("COPAW_AUTH_PASSWORD")
        if env_password:
            self.password = env_password

        env_expire = os.environ.get("COPAW_AUTH_SESSION_EXPIRE_HOURS")
        if env_expire and env_expire.isdigit():
            self.session_expire_hours = int(env_expire)


@dataclass
class Session:
    """Session data structure."""

    username: str
    created_at: float
    expires_at: float


@dataclass
class SessionManager:
    """In-memory session manager."""

    sessions: dict[str, Session] = field(default_factory=dict)

    def create_session(self, username: str, expire_hours: int) -> str:
        """Create a new session and return the token."""
        token = secrets.token_urlsafe(32)
        now = time.time()
        self.sessions[token] = Session(
            username=username,
            created_at=now,
            expires_at=now + expire_hours * 3600,
        )
        return token

    def validate_session(self, token: str) -> Optional[str]:
        """Validate session and return username if valid."""
        session = self.sessions.get(token)
        if session is None:
            return None
        if time.time() > session.expires_at:
            del self.sessions[token]
            return None
        return session.username

    def delete_session(self, token: str) -> None:
        """Delete a session."""
        self.sessions.pop(token, None)

    def cleanup_expired(self) -> None:
        """Remove expired sessions."""
        now = time.time()
        expired = [
            token for token, session in self.sessions.items()
            if now > session.expires_at
        ]
        for token in expired:
            del self.sessions[token]


# Global instances
auth_config = AuthConfig()
session_manager = SessionManager()


# Login page HTML template
LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CoPaw Login</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
        }
        .logo {
            text-align: center;
            margin-bottom: 30px;
        }
        .logo h1 {
            color: #333;
            font-size: 28px;
            margin-top: 10px;
        }
        .logo-icon {
            font-size: 48px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus, input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .error-message {
            background: #fee;
            color: #c00;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: none;
        }
        .login-btn {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .login-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
        .login-btn:active {
            transform: translateY(0);
        }
        .footer {
            text-align: center;
            margin-top: 20px;
            color: #999;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="logo">
            <div class="logo-icon">🐾</div>
            <h1>CoPaw</h1>
        </div>
        <div id="error" class="error-message"></div>
        <form id="loginForm">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required autocomplete="username">
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autocomplete="current-password">
            </div>
            <button type="submit" class="login-btn">Login</button>
        </form>
        <div class="footer">
            Personal AI Assistant
        </div>
    </div>
    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const errorDiv = document.getElementById('error');
            errorDiv.style.display = 'none';

            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;

            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });

                const data = await response.json();

                if (response.ok) {
                    window.location.href = '/';
                } else {
                    errorDiv.textContent = data.detail || 'Login failed';
                    errorDiv.style.display = 'block';
                }
            } catch (err) {
                errorDiv.textContent = 'Network error. Please try again.';
                errorDiv.style.display = 'block';
            }
        });
    </script>
</body>
</html>
"""


def get_session_token_from_request(request: Request) -> Optional[str]:
    """Extract session token from request (cookie or header)."""
    # Try cookie first
    token = request.cookies.get("copaw_session")
    if token:
        return token
    # Try Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def is_public_path(path: str) -> bool:
    """Check if the path should be accessible without authentication."""
    public_paths = {
        "/api/auth/login",
        "/api/auth/logout",
        "/api/version",
        "/logo.png",
        "/copaw-symbol.svg",
    }
    if path in public_paths:
        return True
    if path.startswith("/assets/"):
        return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware for protecting routes."""

    async def dispatch(self, request: Request, call_next):
        # Skip if auth is disabled
        if not auth_config.enabled:
            return await call_next(request)

        path = request.url.path

        # Allow public paths
        if is_public_path(path):
            return await call_next(request)

        # Check session
        token = get_session_token_from_request(request)
        if token:
            username = session_manager.validate_session(token)
            if username:
                # Valid session, proceed
                response = await call_next(request)
                return response

        # Not authenticated
        # For API requests, return 401
        if path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )

        # For page requests, show login page
        return HTMLResponse(content=LOGIN_PAGE_HTML, status_code=200)


def setup_auth(app) -> None:
    """Setup authentication routes and middleware.

    Args:
        app: FastAPI application instance
    """
    from fastapi import Body

    @app.post("/api/auth/login")
    async def login(
        username: str = Body(...),
        password: str = Body(...),
    ):
        """Login endpoint."""
        if not auth_config.enabled:
            return {"message": "Authentication is disabled"}

        if username == auth_config.username and password == auth_config.password:
            token = session_manager.create_session(
                username=username,
                expire_hours=auth_config.session_expire_hours,
            )
            response = JSONResponse(
                content={"message": "Login successful", "username": username}
            )
            response.set_cookie(
                key="copaw_session",
                value=token,
                httponly=True,
                samesite="lax",
                max_age=auth_config.session_expire_hours * 3600,
            )
            return response
        else:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password"
            )

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        """Logout endpoint."""
        token = get_session_token_from_request(request)
        if token:
            session_manager.delete_session(token)
        response = JSONResponse(content={"message": "Logged out"})
        response.delete_cookie("copaw_session")
        return response

    @app.get("/api/auth/status")
    async def auth_status(request: Request):
        """Check authentication status."""
        if not auth_config.enabled:
            return {"authenticated": True, "auth_enabled": False}
        token = get_session_token_from_request(request)
        if token:
            username = session_manager.validate_session(token)
            if username:
                return {"authenticated": True, "username": username, "auth_enabled": True}
        return {"authenticated": False, "auth_enabled": True}

    # Add middleware
    app.add_middleware(AuthMiddleware)