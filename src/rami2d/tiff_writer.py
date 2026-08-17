import tifffile as tifff
from types import GeneratorType
from pathlib import Path
from skimage.util import img_as_float32
from skimage.exposure import rescale_intensity
from skimage.transform import resize,rescale
import dask.array as da
from dask_image.ndfilters import gaussian_filter
from loguru import logger
import queue
import threading
import numpy as np
# local scripts
from .utils_reg import apply_transform


def pyramid_generator(img_arr,levels,color_type="grayscale",down_factor=2):
    
    std_dev=np.ceil((down_factor - 1)/2)
    if (color_type=="RGB" or color_type=="RGBA") :
        height, width = img_arr.shape[0], img_arr.shape[1]
        sigma_value=(std_dev,std_dev,0)
    elif color_type=="grayscale":
        height, width = img_arr.shape
        sigma_value=std_dev

    factor_schedule=[ down_factor**i for i in range(0,levels) ]
    dims_schedule= [np.rint([height/f,width/f]) for f in factor_schedule]
    if (color_type=="RGB" or color_type=="RGBA"):
        dims_schedule=[(*element,3) for element in dims_schedule]
        
    ref_dtype=img_arr.dtype.name
    val_range=(np.min(img_arr), np.max(img_arr))
    
    
    img_aux=img_arr
    for level_index,dims in enumerate(dims_schedule):
        if level_index==0:
            yield img_aux
        else:
            img_dask=da.from_array(img_aux,chunks="auto")
            result=gaussian_filter(img_dask, sigma=sigma_value, order=0,truncate=down_factor)
            img_aux=resize(img_as_float32(result.compute()), dims, order=1, preserve_range=True, anti_aliasing=False)
            img_aux=np.rint(rescale_intensity(img_aux,out_range=val_range) ).astype(ref_dtype)
            yield img_aux


def _pyramid_producer(delayed_img, levels, color_type, q):
    """
    Background thread target:
    Computes Dask arrays and pushes pyramid layers into the queue.
    """
    try:
        for channel_idx, trf_channel in enumerate(delayed_img, start=1):
            # NEW: Tell the consumer we're starting a new channel
            q.put(('channel_start', channel_idx))
            
            # CPU-heavy: compute the full channel
            img_arr = trf_channel.compute()
            
            # CPU-heavy: generate pyramid
            pyramid_layers = pyramid_generator(img_arr, levels, color_type)
            
            # Push each layer. Blocks if queue is full (maxsize=1).
            for layer_index, img_layer in enumerate(pyramid_layers):
                q.put(('data', layer_index, img_layer))
                
    except Exception as e:
        # Pass the exception to the main thread
        q.put(('error', e))
    finally:
        # Sentinel: tells consumer we're done
        q.put(('stop', None))

def _write_tiff_layer(tif, img_layer, layer_index, sublayers, img_data_type, color_type, compression):
    """Write one pyramid layer to the TiffWriter."""
    tif.write(
        img_layer.astype(img_data_type),
        description="",
        subfiletype=0 if layer_index == 0 else 1,
        subifds=sublayers if layer_index == 0 else None,
        metadata=False,
        tile=(256, 256),
        photometric="rgb" if color_type in ("RGB", "RGBA") else "minisblack",
        compression=compression
    )


def write_pyramid(
    delayed_img,
    levels,
    outdir,
    file_name,
    img_data_type,
    color_type,
    compress="default",
    use_queue=True  # NEW: toggle for memory vs. speed
):
    # --- Setup (unchanged) ---
    outdir.mkdir(parents=True, exist_ok=True)
    out_file_path = outdir / file_name

    tiff_compression_opts = [elem.name.lower() for elem in list(tifff.COMPRESSION) if elem.name.lower() != "none"]
    if compress == "default":
        output_file_compression = "jpeg2000" if color_type in ("RGB", "RGBA") else "lzw"
    elif compress == "None":
        print("No compression will be used")
        output_file_compression = None
    elif compress in tiff_compression_opts:
        output_file_compression = compress
    else:
        raise ValueError(f"Compression value {compress} not supported")

    sublayers = levels - 1
    no_of_channels=len(delayed_img)
    logger.info(f"TOTAL CHANNELS TO PROCESS: {no_of_channels}")
    # ----------------------------------------------------
    # 1. QUEUE-BASED PIPELINE (Speed, uses ~2× memory)
    # ----------------------------------------------------
    if use_queue:
        q = queue.Queue(maxsize=1)
        producer_thread = threading.Thread(
            target=_pyramid_producer,
            args=(delayed_img, levels, color_type, q),
            daemon=True
        )
        producer_thread.start()

        with tifff.TiffWriter(out_file_path, ome=False, bigtiff=True) as tif:
            while True:
                item = q.get()
                msg_type = item[0]

                if msg_type == 'stop':
                    break
                elif msg_type == 'error':
                    # Re-raise the producer's exception in the main thread
                    raise item[1]
                elif msg_type == 'channel_start':
                    channel_idx = item[1]
                    logger.info(f"WRITING CHANNEL: {channel_idx}/{no_of_channels} (PYRAMIDAL LEVELS:{levels})")
                else:  # 'data'
                    _, layer_index, img_layer = item
                    _write_tiff_layer(
                        tif,
                        img_layer,
                        layer_index,
                        sublayers,
                        img_data_type,
                        color_type,
                        output_file_compression
                    )

        # Wait for the producer to fully exit
        producer_thread.join(timeout=0.1)

    # ----------------------------------------------------
    # 2. SEQUENTIAL FALLBACK (Memory-saver, no overlap)
    # ----------------------------------------------------
    else:
        with tifff.TiffWriter(out_file_path, ome=False, bigtiff=True) as tif:
            for trf_channel in delayed_img:
                img_arr = trf_channel.compute()
                pyramid_layers = pyramid_generator(img_arr, levels, color_type)
                for layer_index, img_layer in enumerate(pyramid_layers):
                    _write_tiff_layer(
                        tif,
                        img_layer,
                        layer_index,
                        sublayers,
                        img_data_type,
                        color_type,
                        output_file_compression
                    )
    logger.info(f"FINISH WRITING IMAGE WITH {no_of_channels} CHANNELS AND \n {levels} PYRAMIDAL LEVELS")
    return out_file_path