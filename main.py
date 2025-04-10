from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from titiler.core.factory import TilerFactory
from titiler.core.errors import TilerError
from titiler.mosaic.errors import MosaicError
from rio_tiler.io import COGReader
from rio_tiler.errors import RioTilerError
from pyproj import Transformer
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="COG Tile Server", description="A server for serving tiles of Cloud Optimized GeoTIFFs",)

# Constants
DATA_DIR = os.getenv("COG_STORAGE_PATH", "/data")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS").split(",")
DEFAULT_CACHE_CONTROL = os.getenv("DEFAULT_CACHE_CONTROL", "public, max-age=3600")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Create TilerFactory instance
cog = TilerFactory()

# Register TiTiler routes with prefix
app.include_router(cog.router, prefix="/cog")

def transform_bounds(bounds, from_epsg="EPSG:32617", to_epsg="EPSG:4326"):
    """Transform bounds from one CRS to another."""
    transformer = Transformer.from_crs(from_epsg, to_epsg, always_xy=True)
    minx, miny = transformer.transform(bounds[0], bounds[1])
    maxx, maxy = transformer.transform(bounds[2], bounds[3])
    return [minx, miny, maxx, maxy]

def get_full_url(path: str) -> str:
    """Construct full URL for the COG file."""
    # Remove leading slash if present
    path = path.lstrip('/')
    return os.path.join(DATA_DIR, path)

# Custom endpoint for getting COG metadata
@app.get("/metadata/{cog_path:path}")
async def get_cog_metadata(cog_path: str):
    """Get metadata for a COG file."""
    logger.info(f"Fetching metadata for {cog_path}")
    try:
        # full_path = os.path.join(os.getenv("COG_STORAGE_PATH", ""), cog_path)
        full_path = get_full_url(cog_path)

        if not os.path.exists(full_path):
            logger.warning(f"File not found: {cog_path}")
            raise HTTPException(status_code=404, detail=f"File not found: {cog_path}")
        
        with COGReader(full_path) as cog:
            info = cog.info()
            bounds = cog.bounds
            geo_bounds = transform_bounds(bounds)
            band_descriptions = info.band_descriptions
            band_names = [desc[1] for desc in band_descriptions] if band_descriptions else [f"band{i+1}" for i in range(info.count)]
            return {
                "bounds": bounds,
                "geographic_bounds": geo_bounds,
                "minzoom": cog.minzoom,
                "maxzoom": cog.maxzoom,
                "width": cog.width,
                "height": cog.height,
                "crs": str(cog.crs),
                "url": full_path,
                "band_count": info.count,
                "band_names": band_names
            }
    except Exception as e:
        logger.exception(f"Error getting metadata: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Custom endpoint to validate if a file exists
@app.get("/validate/{cog_path:path}")
async def validate_cog(cog_path: str):
    """Validate if a COG file exists and is readable."""
    try:
        full_url = get_full_url(cog_path)
        if not os.path.exists(full_url):
            raise HTTPException(status_code=404, detail=f"File not found: {cog_path}")
        
        with COGReader(full_url) as cog:
            return {
                "status": "valid",
                "path": cog_path,
                "url": full_url
            }
    except Exception as e:
        logger.exception(f"Error validating COG: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
# Error handlers
@app.exception_handler(TilerError)
async def titiler_exception_handler(request, exc):
    return {"detail": str(exc)}

@app.exception_handler(MosaicError)
async def mosaic_exception_handler(request, exc):
    return {"detail": str(exc)}

@app.exception_handler(RioTilerError)
async def riotiler_exception_handler(request, exc):
    return {"detail": str(exc)}

class ErrorResponse(BaseModel):
    detail: str
    timestamp: str
    request_id: str | None = None

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            detail=str(exc.detail),
            timestamp=datetime.utcnow().isoformat(),
            request_id=getattr(request.state, 'request_id', None)
        ).model_dump(),
        headers=exc.headers
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)