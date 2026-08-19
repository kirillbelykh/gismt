import base64
import httpx
from typing import Optional
from app.core.config import settings
from app.core.logging import get_logger


logger = get_logger(__name__)

class CryptoProSigner:
    def __init__(self, thumbprint: Optional[str] = None):
        self.thumbprint = thumbprint

    async def remote_sign(
        self,
        data: str,
        detached: bool,
        cadesbes: bool,
    ) -> str:
        headers: dict[str, str] = {}

        if settings.CRPT_SIGNER_TOKEN:
            headers["X-SIGNER-TOKEN"] = settings.CRPT_SIGNER_TOKEN

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{settings.CRPT_SIGNER_URL}/sign",
                headers=headers,
                json={
                    "data": data,
                    "detached": detached,
                    "cadesbes": cadesbes,
                },
            )
            r.raise_for_status()
            return r.json()["signature"]

    async def sign_data(
        self,
        data_str: str,
        detached: bool = False,
        cadesbes: bool = False,
    ) -> str:

        # 🔹 основной путь — ВСЕГДА через signer-service
        if settings.CRPT_SIGNER_MODE == "remote":
            return await self.remote_sign(data_str, detached, cadesbes)

        # 🔹 mock — для тестов
        if settings.CRPT_MOCK_MODE:
            mock_sig = base64.b64encode(
                f"MOCK_SIGNATURE_{self.thumbprint or 'no-cert'}".encode()
            ).decode()
            logger.info("Using mock signature")
            return mock_sig

        # 🔴 локальной подписи в backend БОЛЬШЕ НЕТ
        raise RuntimeError(
            "Local CryptoPro signing is disabled in backend. "
            "Use signer-service."
        )
