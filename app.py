from fastapi import FastAPI, File, UploadFile, HTTPException, Header, Query
from fastapi.responses import StreamingResponse, PlainTextResponse
from PIL import Image, ImageOps
from io import BytesIO
import os
import imghdr

API_KEY = os.getenv("API_KEY", "")

app = FastAPI(title="Image Normalizer", version="1.0.0")

def check_api_key(x_api_key: str | None):
    if not API_KEY:
        return
    if x_api_key is None or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

@app.get("/health", response_class=PlainTextResponse)
def health():
    return "OK"

@app.post("/normalize")
async def normalize_image(
    image: UploadFile = File(...),
    x_api_key: str | None = Header(default=None, convert_underscores=False),
    fmt: str = Query(default="keep"),      # keep|jpeg|png|webp
    quality: int = Query(default=90, ge=1, le=100),
    strip: bool = Query(default=True),
    optimize: bool = Query(default=True),
):
    check_api_key(x_api_key)

    data = await image.read()
    if not data:
        raise HTTPException(400, "Empty file")

    kind = imghdr.what(None, h=data)
    if kind not in ("jpeg", "png", "webp", "tiff", "bmp", "gif", None):
        raise HTTPException(415, f"Unsupported image type: {kind}")

    try:
        im = Image.open(BytesIO(data))
    except Exception as e:
        raise HTTPException(415, f"Cannot open image: {e}")

    # применяем EXIF-поворот и тем самым нормализуем пиксели
    im = ImageOps.exif_transpose(im)

    in_format = (im.format or "").lower()
    if fmt == "keep":
        out_format = in_format if in_format in ("jpeg", "png", "webp") else "jpeg"
    else:
        out_format = fmt.lower()
        if out_format not in ("jpeg", "png", "webp"):
            raise HTTPException(400, "fmt must be keep|jpeg|png|webp")

    save_params = {}
    if out_format in ("jpeg", "webp"):
        save_params["quality"] = quality
    if strip:
        im.info.pop("exif", None)
    if optimize:
        save_params["optimize"] = True
    if out_format == "jpeg":
        save_params.setdefault("progressive", True)
        save_params.setdefault("subsampling", "4:2:0")

    if out_format == "jpeg" and im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1] if im.mode in ("RGBA", "LA") else None)
        im = bg
    elif out_format in ("png", "webp") and im.mode == "P":
        im = im.convert("RGBA")

    buf = BytesIO()
    im.save(buf, format=out_format.upper(), **save_params)
    buf.seek(0)

    mime = {"jpeg":"image/jpeg","png":"image/png","webp":"image/webp"}[out_format]
    headers = {"Cache-Control":"no-store","X-Processed":"auto-orient,strip"}

    return StreamingResponse(buf, media_type=mime, headers=headers)
