# ============= Push Notification Service =============
"""
Firebase Cloud Messaging (FCM) HTTP v1 API push notification service.

This service is DISABLED by default. To enable:

OPTION 1 - Service Account JSON file (recommended):
1. Go to Firebase Console -> Project Settings -> Service accounts
2. Click "Generate new private key" to download the JSON file
3. Set GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
4. Set FCM_PROJECT_ID=your-firebase-project-id

OPTION 2 - Service Account JSON as environment variable:
1. Set FCM_SERVICE_ACCOUNT_JSON with the JSON content (for containerized deployments)
2. Set FCM_PROJECT_ID=your-firebase-project-id

The FCM_ENABLED environment variable can be set to explicitly enable/disable.
"""

import os
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import asyncio

logger = logging.getLogger(__name__)

# ============= Check Dependencies =============
HTTPX_AVAILABLE = False
GOOGLE_AUTH_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    logger.info("httpx not installed - push notifications disabled")

try:
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    logger.info("google-auth not installed - push notifications disabled")

# ============= Configuration =============
FCM_PROJECT_ID = os.getenv("FCM_PROJECT_ID", "")
FCM_SERVICE_ACCOUNT_JSON = os.getenv("FCM_SERVICE_ACCOUNT_JSON", "")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

# Check if FCM is configured
_fcm_configured = bool(FCM_PROJECT_ID) and (bool(GOOGLE_APPLICATION_CREDENTIALS) or bool(FCM_SERVICE_ACCOUNT_JSON))
FCM_ENABLED = os.getenv("FCM_ENABLED", "").lower() in ("true", "1", "yes") or _fcm_configured

# FCM HTTP v1 API endpoint
FCM_API_URL_TEMPLATE = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

# OAuth 2.0 scope for FCM
FCM_SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]


# ============= Notification Types =============
class NotificationType:
    """Standard notification types for the app."""
    NEW_QUESTION = "new_question"
    DAILY_REMINDER = "daily_reminder"
    RESULTS_AVAILABLE = "results_available"
    STREAK_WARNING = "streak_warning"


def is_push_enabled() -> bool:
    """Check if push notifications are enabled and configured."""
    return (
        FCM_ENABLED and 
        bool(FCM_PROJECT_ID) and 
        (bool(GOOGLE_APPLICATION_CREDENTIALS) or bool(FCM_SERVICE_ACCOUNT_JSON)) and
        HTTPX_AVAILABLE and 
        GOOGLE_AUTH_AVAILABLE
    )


def get_push_status() -> Dict[str, Any]:
    """Get the current push notification configuration status."""
    return {
        "enabled": is_push_enabled(),
        "api_version": "v1",
        "project_id_configured": bool(FCM_PROJECT_ID),
        "credentials_configured": bool(GOOGLE_APPLICATION_CREDENTIALS) or bool(FCM_SERVICE_ACCOUNT_JSON),
        "httpx_available": HTTPX_AVAILABLE,
        "google_auth_available": GOOGLE_AUTH_AVAILABLE,
        "reason": _get_disabled_reason() if not is_push_enabled() else None
    }


def _get_disabled_reason() -> Optional[str]:
    """Get the reason why push notifications are disabled."""
    if not HTTPX_AVAILABLE:
        return "httpx package not installed (pip install httpx)"
    if not GOOGLE_AUTH_AVAILABLE:
        return "google-auth package not installed (pip install google-auth)"
    if not FCM_PROJECT_ID:
        return "FCM_PROJECT_ID environment variable not set"
    if not GOOGLE_APPLICATION_CREDENTIALS and not FCM_SERVICE_ACCOUNT_JSON:
        return "No credentials configured (set GOOGLE_APPLICATION_CREDENTIALS or FCM_SERVICE_ACCOUNT_JSON)"
    if not FCM_ENABLED:
        return "FCM_ENABLED is explicitly set to false"
    return None


class FCMServiceV1:
    """
    Firebase Cloud Messaging HTTP v1 API service.
    
    Uses OAuth 2.0 with service account credentials for authentication.
    This is the modern, recommended API with better features and long-term support.
    """
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.api_url = FCM_API_URL_TEMPLATE.format(project_id=project_id)
        self._client: Optional[httpx.AsyncClient] = None
        self._credentials = None
        self._credentials_lock = asyncio.Lock()
    
    def _load_credentials(self):
        """Load service account credentials."""
        if self._credentials is not None:
            return self._credentials
        
        try:
            if FCM_SERVICE_ACCOUNT_JSON:
                # Load from environment variable (JSON string)
                service_account_info = json.loads(FCM_SERVICE_ACCOUNT_JSON)
                self._credentials = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=FCM_SCOPES
                )
            elif GOOGLE_APPLICATION_CREDENTIALS:
                # Load from file path
                self._credentials = service_account.Credentials.from_service_account_file(
                    GOOGLE_APPLICATION_CREDENTIALS,
                    scopes=FCM_SCOPES
                )
            else:
                raise ValueError("No credentials configured")
                
            logger.info("FCM service account credentials loaded successfully")
            return self._credentials
            
        except Exception as e:
            logger.error(f"Failed to load FCM credentials: {e}")
            raise
    
    async def _get_access_token(self) -> str:
        """Get a valid OAuth 2.0 access token, refreshing if needed."""
        async with self._credentials_lock:
            credentials = self._load_credentials()
            
            # Check if token needs refresh
            if not credentials.valid:
                # Run the blocking refresh in a thread pool
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: credentials.refresh(Request())
                )
            
            return credentials.token
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    def _build_message(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None,
        badge: Optional[int] = None
    ) -> Dict[str, Any]:
        """Build a single FCM v1 message payload."""
        message = {
            "token": token,
            "notification": {
                "title": title,
                "body": body
            },
            "android": {
                "priority": "high",
                "notification": {
                    "channel_id": "daily_questions",
                    "sound": "default"
                }
            },
            "apns": {
                "payload": {
                    "aps": {
                        "sound": "default",
                        "badge": badge if badge is not None else 1
                    }
                }
            },
            "webpush": {
                "notification": {
                    "icon": "/icon-192.png"
                }
            }
        }
        
        if data:
            message["data"] = data
        
        return message
    
    async def send_to_token(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None,
        badge: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Send push notification to a single device token.
        
        Args:
            token: FCM device token
            title: Notification title
            body: Notification body text
            data: Optional data payload (key-value pairs, all strings)
            badge: Optional badge count for iOS
            
        Returns:
            FCM API response
        """
        if not is_push_enabled():
            logger.debug(f"Push disabled - would send to token: {title}")
            return {"success": False, "message": "Push notifications disabled"}
        
        try:
            access_token = await self._get_access_token()
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "message": self._build_message(token, title, body, data, badge)
            }
            
            client = await self._get_client()
            response = await client.post(
                self.api_url,
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"FCM v1 send success: {result.get('name', 'unknown')}")
                return {"success": True, "message_id": result.get("name")}
            else:
                error_data = response.json() if response.content else {}
                logger.error(f"FCM v1 send failed: {response.status_code} - {error_data}")
                return {
                    "success": False, 
                    "error": error_data.get("error", {}).get("message", "Unknown error"),
                    "status_code": response.status_code
                }
                
        except Exception as e:
            logger.error(f"FCM v1 send failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_to_tokens(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None,
        badge: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Send push notification to multiple device tokens.
        
        Note: FCM v1 API doesn't support batch sending in a single request,
        so we send to each token individually with concurrency control.
        
        Args:
            tokens: List of FCM device tokens
            title: Notification title
            body: Notification body text
            data: Optional data payload (key-value pairs, all strings)
            badge: Optional badge count for iOS
            
        Returns:
            Aggregated results with success/failure counts
        """
        if not tokens:
            return {"success": 0, "failure": 0, "message": "No tokens provided"}
        
        if not is_push_enabled():
            logger.debug(f"Push disabled - would send to {len(tokens)} tokens: {title}")
            return {"success": 0, "failure": 0, "message": "Push notifications disabled"}
        
        # Limit concurrent requests to avoid rate limiting
        semaphore = asyncio.Semaphore(10)
        
        async def send_with_semaphore(token: str) -> Dict[str, Any]:
            async with semaphore:
                return await self.send_to_token(token, title, body, data, badge)
        
        # Send to all tokens concurrently (with limit)
        results = await asyncio.gather(
            *[send_with_semaphore(token) for token in tokens],
            return_exceptions=True
        )
        
        success_count = 0
        failure_count = 0
        failed_tokens = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failure_count += 1
                failed_tokens.append(tokens[i])
            elif result.get("success"):
                success_count += 1
            else:
                failure_count += 1
                # Check for invalid token errors
                error = result.get("error", "")
                if "not a valid FCM registration token" in str(error).lower():
                    failed_tokens.append(tokens[i])
        
        logger.info(f"FCM v1 batch send: success={success_count}, failure={failure_count}")
        
        return {
            "success": success_count,
            "failure": failure_count,
            "failed_tokens": failed_tokens  # Can be used to clean up invalid tokens
        }
    
    async def send_to_topic(
        self,
        topic: str,
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Send push notification to all devices subscribed to a topic.
        
        Args:
            topic: Topic name (e.g., "group_abc123")
            title: Notification title
            body: Notification body text
            data: Optional data payload
            
        Returns:
            FCM API response
        """
        if not is_push_enabled():
            logger.debug(f"Push disabled - would send to topic {topic}: {title}")
            return {"success": False, "message": "Push notifications disabled"}
        
        try:
            access_token = await self._get_access_token()
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            message = {
                "topic": topic,
                "notification": {
                    "title": title,
                    "body": body
                },
                "android": {
                    "priority": "high",
                    "notification": {
                        "channel_id": "daily_questions",
                        "sound": "default"
                    }
                },
                "apns": {
                    "payload": {
                        "aps": {
                            "sound": "default"
                        }
                    }
                }
            }
            
            if data:
                message["data"] = data
            
            payload = {"message": message}
            
            client = await self._get_client()
            response = await client.post(
                self.api_url,
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"FCM v1 topic send to '{topic}': {result.get('name', 'success')}")
                return {"success": True, "message_id": result.get("name")}
            else:
                error_data = response.json() if response.content else {}
                logger.error(f"FCM v1 topic send failed: {response.status_code} - {error_data}")
                return {"success": False, "error": error_data}
                
        except Exception as e:
            logger.error(f"FCM v1 topic send failed: {e}")
            return {"success": False, "error": str(e)}


# ============= Global Service Instance =============
_fcm_service: Optional[FCMServiceV1] = None


def get_fcm_service() -> Optional[FCMServiceV1]:
    """Get the global FCM service instance (creates if needed)."""
    global _fcm_service
    
    if not is_push_enabled():
        return None
    
    if _fcm_service is None:
        _fcm_service = FCMServiceV1(project_id=FCM_PROJECT_ID)
    
    return _fcm_service


# ============= Convenience Functions =============

async def notify_new_question(
    group_id: str,
    group_name: str,
    question_text: str,
    tokens: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Send notification when a new daily question is created.
    """
    service = get_fcm_service()
    if not service:
        return {"sent": False, "reason": "Push notifications disabled"}
    
    title = f"New Question in {group_name}! 🎯"
    body = question_text[:100] + ("..." if len(question_text) > 100 else "")
    data = {
        "type": NotificationType.NEW_QUESTION,
        "group_id": group_id,
        "click_action": "OPEN_QUESTION"
    }
    
    if tokens:
        result = await service.send_to_tokens(tokens, title, body, data)
    else:
        topic = f"group_{group_id.replace('-', '_')}"
        result = await service.send_to_topic(topic, title, body, data)
    
    return {"sent": True, **result}


async def notify_daily_reminder(
    group_id: str,
    group_name: str,
    tokens: List[str],
    streak_count: Optional[int] = None
) -> Dict[str, Any]:
    """
    Send reminder to users who haven't answered today's question.
    """
    service = get_fcm_service()
    if not service:
        return {"sent": False, "reason": "Push notifications disabled"}
    
    if streak_count and streak_count > 0:
        title = f"Don't break your {streak_count}-day streak! 🔥"
    else:
        title = "Daily Question Waiting! ⏰"
    
    body = f"You haven't answered today's question in {group_name}"
    data = {
        "type": NotificationType.DAILY_REMINDER,
        "group_id": group_id,
        "click_action": "OPEN_QUESTION"
    }
    
    result = await service.send_to_tokens(tokens, title, body, data)
    return {"sent": True, **result}


async def notify_results_available(
    group_id: str,
    group_name: str,
    winner: Optional[str] = None,
    tokens: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Send notification when voting results are available.
    """
    service = get_fcm_service()
    if not service:
        return {"sent": False, "reason": "Push notifications disabled"}
    
    title = "Results are in! 📊"
    body = f"See who won in {group_name}" if not winner else f"{winner} won in {group_name}!"
    data = {
        "type": NotificationType.RESULTS_AVAILABLE,
        "group_id": group_id,
        "click_action": "OPEN_RESULTS"
    }
    
    if tokens:
        result = await service.send_to_tokens(tokens, title, body, data)
    else:
        topic = f"group_{group_id.replace('-', '_')}"
        result = await service.send_to_topic(topic, title, body, data)
    
    return {"sent": True, **result}


# ============= Startup Message =============
def log_push_status():
    """Log the push notification configuration status on startup."""
    status = get_push_status()
    if status["enabled"]:
        logger.info(f"✅ Push notifications ENABLED (FCM HTTP v1 API, project: {FCM_PROJECT_ID})")
    else:
        logger.info(f"ℹ️  Push notifications DISABLED: {status['reason']}")


# ============= Push Service Wrapper =============
class PushService:
    """
    Wrapper class providing a simplified interface for push notifications.
    This is the main entry point used by the application.
    """
    
    def is_enabled(self) -> bool:
        """Check if push notifications are enabled and configured."""
        return is_push_enabled()
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current push notification configuration status."""
        return get_push_status()
    
    async def send_daily_question_notification(
        self,
        tokens: List[str],
        group_name: str,
        question_preview: str
    ) -> Dict[str, Any]:
        """
        Send notification when a new daily question is available.
        
        Args:
            tokens: List of FCM device tokens
            group_name: Name of the group
            question_preview: First 100 chars of the question text
            
        Returns:
            FCM API response with success/failure counts
        """
        service = get_fcm_service()
        if not service:
            return {"sent": False, "reason": "Push notifications disabled"}
        
        title = f"New Question in {group_name}! 🎯"
        body = question_preview + ("..." if len(question_preview) >= 100 else "")
        data = {
            "type": NotificationType.NEW_QUESTION,
            "click_action": "OPEN_QUESTION"
        }
        
        result = await service.send_to_tokens(tokens, title, body, data)
        return {"sent": True, **result}
    
    async def send_reminder_notification(
        self,
        tokens: List[str],
        group_name: str,
        streak_count: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Send reminder to users who haven't answered today's question.
        
        Args:
            tokens: List of FCM device tokens
            group_name: Name of the group
            streak_count: User's current streak (optional)
            
        Returns:
            FCM API response with success/failure counts
        """
        service = get_fcm_service()
        if not service:
            return {"sent": False, "reason": "Push notifications disabled"}
        
        if streak_count and streak_count > 0:
            title = f"Don't break your {streak_count}-day streak! 🔥"
        else:
            title = "Daily Question Waiting! ⏰"
        
        body = f"You haven't answered today's question in {group_name}"
        data = {
            "type": NotificationType.DAILY_REMINDER,
            "click_action": "OPEN_QUESTION"
        }
        
        result = await service.send_to_tokens(tokens, title, body, data)
        return {"sent": True, **result}
    
    async def send_results_notification(
        self,
        tokens: List[str],
        group_name: str,
        winner: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send notification when voting results are available.
        
        Args:
            tokens: List of FCM device tokens
            group_name: Name of the group
            winner: Name of the winner (optional)
            
        Returns:
            FCM API response with success/failure counts
        """
        service = get_fcm_service()
        if not service:
            return {"sent": False, "reason": "Push notifications disabled"}
        
        title = "Results are in! 📊"
        body = f"See who won in {group_name}" if not winner else f"{winner} won in {group_name}!"
        data = {
            "type": NotificationType.RESULTS_AVAILABLE,
            "click_action": "OPEN_RESULTS"
        }
        
        result = await service.send_to_tokens(tokens, title, body, data)
        return {"sent": True, **result}


# Global push service instance
push_service = PushService()
