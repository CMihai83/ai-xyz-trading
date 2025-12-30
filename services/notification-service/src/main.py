"""
Notification Service - Multi-channel alert and notification system.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import structlog

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Notification Service",
    description="Multi-channel alert and notification system",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class NotificationRequest(BaseModel):
    title: str
    message: str
    severity: str  # info, warning, error, critical
    channels: List[str]  # email, sms, webhook, slack
    recipients: List[str]
    metadata: Optional[Dict[str, Any]] = None

class NotificationHistory(BaseModel):
    notification_id: str
    title: str
    message: str
    severity: str
    channels: List[str]
    recipients: List[str]
    status: str
    sent_at: datetime
    delivered_at: Optional[datetime] = None

class NotificationService:
    """Multi-channel notification service."""
    
    def __init__(self):
        self.notification_history = []
        self.channels = {
            'email': self.send_email,
            'sms': self.send_sms,
            'webhook': self.send_webhook,
            'slack': self.send_slack,
            'console': self.send_console
        }
        
        # Configuration (in production, these would be environment variables)
        self.email_config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'your-email@gmail.com',
            'password': 'your-app-password'
        }
    
    async def send_notification(self, request: NotificationRequest) -> NotificationHistory:
        """Send notification through specified channels."""
        notification_id = f"notif_{int(datetime.now().timestamp())}"
        
        # Create notification history entry
        notification = NotificationHistory(
            notification_id=notification_id,
            title=request.title,
            message=request.message,
            severity=request.severity,
            channels=request.channels,
            recipients=request.recipients,
            status="sending",
            sent_at=datetime.now()
        )
        
        # Send through each channel
        success_count = 0
        for channel in request.channels:
            if channel in self.channels:
                try:
                    await self.channels[channel](request)
                    success_count += 1
                    logger.info(f"Notification sent via {channel}", 
                               notification_id=notification_id)
                except Exception as e:
                    logger.error(f"Failed to send notification via {channel}: {str(e)}")
        
        # Update status
        if success_count == len(request.channels):
            notification.status = "delivered"
            notification.delivered_at = datetime.now()
        elif success_count > 0:
            notification.status = "partial"
        else:
            notification.status = "failed"
        
        # Store in history
        self.notification_history.append(notification)
        
        # Keep only last 1000 notifications
        if len(self.notification_history) > 1000:
            self.notification_history = self.notification_history[-1000:]
        
        return notification
    
    async def send_email(self, request: NotificationRequest):
        """Send email notification."""
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.email_config['username']
            msg['Subject'] = f"[{request.severity.upper()}] {request.title}"
            
            # Email body
            body = f"""
            Alert: {request.title}
            Severity: {request.severity.upper()}
            Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            Message:
            {request.message}
            
            ---
            AI Trading System Notification
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send to each recipient
            server = smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port'])
            server.starttls()
            server.login(self.email_config['username'], self.email_config['password'])
            
            for recipient in request.recipients:
                msg['To'] = recipient
                text = msg.as_string()
                server.sendmail(self.email_config['username'], recipient, text)
            
            server.quit()
            
        except Exception as e:
            logger.error(f"Email sending failed: {str(e)}")
            # In production, we might want to use a more robust email service
            pass
    
    async def send_sms(self, request: NotificationRequest):
        """Send SMS notification."""
        # Placeholder for SMS implementation
        # In production, this would integrate with services like Twilio
        logger.info(f"SMS notification: {request.title} - {request.message}")
        await asyncio.sleep(0.1)  # Simulate API call
    
    async def send_webhook(self, request: NotificationRequest):
        """Send webhook notification."""
        # Placeholder for webhook implementation
        logger.info(f"Webhook notification: {request.title} - {request.message}")
        await asyncio.sleep(0.1)  # Simulate API call
    
    async def send_slack(self, request: NotificationRequest):
        """Send Slack notification."""
        # Placeholder for Slack implementation
        logger.info(f"Slack notification: {request.title} - {request.message}")
        await asyncio.sleep(0.1)  # Simulate API call
    
    async def send_console(self, request: NotificationRequest):
        """Send console notification (for development)."""
        severity_colors = {
            'info': '\033[94m',      # Blue
            'warning': '\033[93m',   # Yellow
            'error': '\033[91m',     # Red
            'critical': '\033[95m'   # Magenta
        }
        
        color = severity_colors.get(request.severity, '\033[0m')
        reset_color = '\033[0m'
        
        print(f"\n{color}[{request.severity.upper()}] {request.title}{reset_color}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Message: {request.message}")
        print(f"Recipients: {', '.join(request.recipients)}")
        print("-" * 50)
    
    def get_notification_history(self, limit: int = 100) -> List[NotificationHistory]:
        """Get notification history."""
        return self.notification_history[-limit:]
    
    def get_notification_stats(self) -> Dict[str, Any]:
        """Get notification statistics."""
        total_notifications = len(self.notification_history)
        
        if total_notifications == 0:
            return {
                'total_notifications': 0,
                'success_rate': 0.0,
                'by_severity': {},
                'by_channel': {},
                'by_status': {}
            }
        
        # Count by severity
        severity_counts = {}
        for notif in self.notification_history:
            severity_counts[notif.severity] = severity_counts.get(notif.severity, 0) + 1
        
        # Count by status
        status_counts = {}
        for notif in self.notification_history:
            status_counts[notif.status] = status_counts.get(notif.status, 0) + 1
        
        # Count by channel
        channel_counts = {}
        for notif in self.notification_history:
            for channel in notif.channels:
                channel_counts[channel] = channel_counts.get(channel, 0) + 1
        
        # Calculate success rate
        successful = status_counts.get('delivered', 0) + status_counts.get('partial', 0)
        success_rate = (successful / total_notifications) * 100
        
        return {
            'total_notifications': total_notifications,
            'success_rate': success_rate,
            'by_severity': severity_counts,
            'by_channel': channel_counts,
            'by_status': status_counts
        }

# Initialize notification service
notification_service = NotificationService()

@app.get("/")
async def root():
    return {
        "service": "notification-service",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "available_channels": list(notification_service.channels.keys())
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "notification-service",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/send", response_model=NotificationHistory)
async def send_notification(request: NotificationRequest):
    """Send a notification."""
    try:
        notification = await notification_service.send_notification(request)
        return notification
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sending notification: {str(e)}")

@app.get("/history")
async def get_notification_history(limit: int = 100):
    """Get notification history."""
    try:
        history = notification_service.get_notification_history(limit)
        return {
            "notifications": history,
            "count": len(history),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting notification history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting notification history: {str(e)}")

@app.get("/stats")
async def get_notification_stats():
    """Get notification statistics."""
    try:
        stats = notification_service.get_notification_stats()
        return {
            "stats": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting notification stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting notification stats: {str(e)}")

@app.get("/channels")
async def get_available_channels():
    """Get available notification channels."""
    return {
        "channels": list(notification_service.channels.keys()),
        "count": len(notification_service.channels),
        "timestamp": datetime.now().isoformat()
    }

# Convenience endpoints for common notifications
@app.post("/alerts/trading")
async def send_trading_alert(symbol: str, action: str, price: float, message: str):
    """Send trading alert notification."""
    request = NotificationRequest(
        title=f"Trading Alert: {action} {symbol}",
        message=f"{message}\nSymbol: {symbol}\nAction: {action}\nPrice: ${price}",
        severity="info",
        channels=["console", "email"],
        recipients=["trader@example.com"]
    )
    
    return await send_notification(request)

@app.post("/alerts/risk")
async def send_risk_alert(risk_type: str, current_value: float, limit: float, severity: str = "warning"):
    """Send risk alert notification."""
    request = NotificationRequest(
        title=f"Risk Alert: {risk_type}",
        message=f"Risk limit exceeded!\n{risk_type}: {current_value}\nLimit: {limit}",
        severity=severity,
        channels=["console", "email"],
        recipients=["risk@example.com"]
    )
    
    return await send_notification(request)

@app.post("/alerts/system")
async def send_system_alert(component: str, status: str, message: str, severity: str = "error"):
    """Send system alert notification."""
    request = NotificationRequest(
        title=f"System Alert: {component}",
        message=f"Component: {component}\nStatus: {status}\nDetails: {message}",
        severity=severity,
        channels=["console", "email"],
        recipients=["admin@example.com"]
    )
    
    return await send_notification(request)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
