from itsdangerous import URLSafeSerializer

from reviewpilot.config import get_settings


def get_session_serializer() -> URLSafeSerializer:
    settings = get_settings()
    return URLSafeSerializer(settings.app_secret_key, salt="reviewpilot-session")
