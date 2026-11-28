import os

# Ключ шифрования обязателен (см. Settings.require_secret); для тестов задаём фиксированный.
os.environ.setdefault("APP_SECRET", "test-only-secret-0123456789abcdef0123456789abcdef")
