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

# @app.get("/tiles/{cog_path:path}/{z}/{x}/{y}", responses={200: {"content": {"image/png": {}}}})
# async def get_tile(
#     cog_path: str,
#     z: int = Path(..., description="Tile zoom level"),
#     x: int = Path(..., description="Tile x index"),
#     y: int = Path(..., description="Tile y index"),
#     format: str = Query("png", description="Output image format"),
#     bidx: List[int] = Query([1, 2, 3], description="Band indices"),
#     rescale: Optional[str] = Query(None, description="Min,Max rescaling range"),
#     colormap_name: Optional[str] = Query(None, description="Colormap name"),
#     resampling_method: str = Query("bilinear", description="Resampling method")
# ):
#     """Get a map tile from a COG file."""
#     try:
#         file_path = get_full_url(cog_path)
#         logger.debug(f"Getting tile z={z} x={x} y={y} from {file_path}")
        
#         if not os.path.exists(file_path):
#             raise HTTPException(status_code=404, detail=f"File not found: {cog_path}")
        
#         # Generate the tile bounds in Web Mercator
#         tile_bounds = mercantile.bounds(x, y, z)
        
#         # Open the COG file
#         with COGReader(file_path) as cog:
#             # Get the source CRS from the COG
#             src_crs = cog.crs
            
#             # Transform the tile bounds to the CRS of the source data
#             if str(src_crs) != "EPSG:3857":  # If not already Web Mercator
#                 bounds = rio_transform_bounds(
#                     "EPSG:3857", 
#                     str(src_crs), 
#                     tile_bounds.west, 
#                     tile_bounds.south, 
#                     tile_bounds.east, 
#                     tile_bounds.north
#                 )
#             else:
#                 bounds = (tile_bounds.west, tile_bounds.south, tile_bounds.east, tile_bounds.north)
            
#             # Read the data for the tile
#             tile_data = cog.tile(x, y, z, tilesize=256, resampling_method=resampling_method, indexes=bidx)
            
#             # Set up rescaling if provided
#             # rescale_params = None
#             # if rescale:
#             #     try:
#             #         rescale_min, rescale_max = map(float, rescale.split(","))
#             #         rescale_params = [(rescale_min, rescale_max)] * len(bidx)
#             #     except ValueError:
#             #         logger.warning(f"Invalid rescale parameter: {rescale}")
            
#             # Render the tile
#             content = render(
#                 tile_data.data,
#                 img_format=format,
#                 colormap=colormap_name,
#             )
            
#             # Return the image response
#             media_type = f"image/{format}" if format != "jpg" else "image/jpeg"
#             return Response(content=content, media_type=media_type)
            
#     except Exception as e:
#         logger.error(f"Error generating tile: {str(e)}", exc_info=True)
#         raise HTTPException(status_code=500, detail=str(e))
    
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