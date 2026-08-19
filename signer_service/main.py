from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from crypto import CryptoProSigner
from config import settings
from logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="CryptoPro Signer Service",
    version="1.0.0",
)

signer = CryptoProSigner()


# ---------- DTO ----------

class SignRequest(BaseModel):
    data: str
    detached: bool = False
    cadesbes: bool = False


class SignResponse(BaseModel):
    signature: str


# ---------- Middleware (минимальная защита) ----------

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if settings.SIGNER_TOKEN:
        token = request.headers.get("X-SIGNER-TOKEN")
        if token != settings.SIGNER_TOKEN:
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
            )
    return await call_next(request)


# ---------- Routes ----------

@app.post("/sign", response_model=SignResponse)
def sign(req: SignRequest):
    """
    Create CryptoPro signature for given data.

    This endpoint is synchronous by design:
    - CryptoPro COM
    - cryptcp
    are blocking operations.
    """
    try:
        signature = signer.sign_data(
            data_str=req.data,
            detached=req.detached,
            cadesbes=req.cadesbes,
        )
        return SignResponse(signature=signature)

    except Exception as e:
        logger.exception("Signing failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# ---------- Healthcheck ----------

@app.get("/health")
def health():
    return {"status": "ok"}
