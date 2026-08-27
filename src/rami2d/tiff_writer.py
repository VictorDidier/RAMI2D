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
import zarr
import zarr.codecs as zarr_codecs
from ome_zarr.writer import write_multiscale
from numcodecs import Blosc,Zlib, Zstd
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



def validate_compression(compress):
    tiff_compression_opts=[element.name.lower() for element in list(tifff.COMPRESSION) if not element.name.lower()=="none"]

    if compress=="default":
        output_file_compression="jpeg2000" if color_type in ("RGB","RGBA") else "lzw"
    elif compress=="None":
        output_file_compression=None
    elif compress in tiff_compression_opts:
        output_file_compression=compress
    else:
        raise ValueError(f"Compression value {compress} not supported")




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




def _get_zarr_v3_codec(compress):
    """Return a zarr v3 codec object (or None) for compression."""
    if compress is None or str(compress).lower() == "none":
        return None
    if str(compress).lower() == "default":
        return zarr_codecs.BloscCodec(cname='lz4', clevel=5, shuffle='shuffle')
    if isinstance(compress, str):
        comp_map = {
            "zlib": zarr_codecs.ZlibCodec(level=6),
            "blosc": zarr_codecs.BloscCodec(cname='lz4', clevel=5, shuffle='shuffle'),
            "lz4": zarr_codecs.BloscCodec(cname='lz4', clevel=5, shuffle='shuffle'),
            "zstd": zarr_codecs.ZstdCodec(level=5),
        }
        if compress.lower() in comp_map:
            return comp_map[compress.lower()]
        raise ValueError(f"Compression {compress} not supported for OME-Zarr v3")
    # Assume it's already a zarr codec or compatible
    return compress


def _get_zarr_compressor(compress):
    """Map the compression argument to a zarr compressor."""
    if compress is None or str(compress).lower() == "none":
        return None
    if str(compress).lower() == "default":
        # Use a safe default compatible with most zarr versions
        return Blosc(cname='lz4', clevel=5, shuffle=Blosc.SHUFFLE)
    if isinstance(compress, str):
        comp_map = {
            "zlib": Zlib(level=6),
            "blosc": Blosc(cname='lz4', clevel=5, shuffle=Blosc.SHUFFLE),
            "lz4": Blosc(cname='lz4', clevel=5, shuffle=Blosc.SHUFFLE),
            "zstd": Zstd(level=5),
        }
        if compress.lower() in comp_map:
            return comp_map[compress.lower()]
        raise ValueError(f"Compression {compress} not supported for OME-Zarr")
    # assume a compressor object was passed
    return compress


def _expand_dims(img_layer, color_type):
    """
    Add singleton t,z dimensions and place channel axis correctly.
    - grayscale: (H,W) -> (1,1,1,H,W)
    - RGB/RGBA:  (H,W,C) -> (1,C,1,H,W)
    """
    if img_layer.ndim == 2:                     # grayscale
        return img_layer[None, None, None, :, :]
    elif img_layer.ndim == 3 and color_type in ("RGB", "RGBA"):
        return img_layer[None, :, None, :, :]   # channel axis = 1
    else:
        raise ValueError(
            f"Unexpected array shape {img_layer.shape} for color_type {color_type}"
        )


def write_pyramid_omezarr(
    delayed_img,
    levels,
    outdir,
    file_name,
    img_data_type,
    color_type,
    compress="default",
    use_queue=True
):
    """
    Write pyramidal image(s) as OME-Zarr, analogous to write_pyramid.

    Each channel in `delayed_img` is stored as a separate OME-Zarr multiscale
    group under the root group. The root group itself does not contain a
    multiscales metadata block (only the sub-groups do), which mirrors the
    multi-series behaviour of the TIFF writer.

    Parameters match write_pyramid.
    """
    outdir.mkdir(parents=True, exist_ok=True)

    # Ensure a .zarr suffix for the store directory
    zarr_path = outdir / file_name
    if not str(zarr_path).endswith(".zarr"):
        zarr_path = outdir / (file_name + ".zarr")

    root = zarr.open_group(str(zarr_path), mode="w")
    compressor = _get_zarr_compressor(compress)

    axes = "tczyx"
    # Coordinate transformations: level i has scale 2**i along y,x
    coordinate_transformations = [
        [{"type": "scale", "scale": [1, 1, 1, 2**i, 2**i]}]
        for i in range(levels)
    ]

    no_of_channels = len(delayed_img)
    logger.info(f"TOTAL CHANNELS TO PROCESS: {no_of_channels}")

    # ------------------------------------------------------------
    # 1. QUEUE-BASED PIPELINE (streams channels, low memory)
    # ------------------------------------------------------------
    if use_queue:
        q = queue.Queue(maxsize=1)
        producer_thread = threading.Thread(
            target=_pyramid_producer,
            args=(delayed_img, levels, color_type, q),
            daemon=True
        )
        producer_thread.start()

        current_channel_group = None
        current_channel_pyramid = []

        while True:
            item = q.get()
            msg_type = item[0]

            if msg_type == "stop":
                break
            elif msg_type == "error":
                raise item[1]
            elif msg_type == "channel_start":
                channel_idx = item[1]
                # Create sub-group for this channel (0-based index)
                group_name = str(channel_idx - 1)
                current_channel_group = root.create_group(group_name)
                current_channel_pyramid = []
                logger.info(
                    f"WRITING CHANNEL: {channel_idx}/{no_of_channels} "
                    f"(PYRAMIDAL LEVELS:{levels})"
                )
            else:  # 'data'
                _, layer_index, img_layer = item
                # Cast to requested dtype and expand to 5D
                img_layer = img_layer.astype(img_data_type)
                img_layer_5d = _expand_dims(img_layer, color_type)
                current_channel_pyramid.append(img_layer_5d)

                # When all levels for this channel have arrived, write them
                if layer_index == levels - 1:
                    write_multiscale(
                        current_channel_pyramid,
                        current_channel_group,
                        axes=axes,
                        coordinate_transformations=coordinate_transformations,
                        compressor=compressor,
                    )
        producer_thread.join(timeout=0.1)

    # ------------------------------------------------------------
    # 2. SEQUENTIAL FALLBACK (simpler, no threading)
    # ------------------------------------------------------------
    else:
        for channel_idx, trf_channel in enumerate(delayed_img, start=1):
            group_name = str(channel_idx - 1)
            channel_group = root.create_group(group_name)
            logger.info(
                f"WRITING CHANNEL: {channel_idx}/{no_of_channels} "
                f"(PYRAMIDAL LEVELS:{levels})"
            )

            img_arr = trf_channel.compute()
            pyramid_layers = pyramid_generator(img_arr, levels, color_type)

            pyramid_5d = []
            for img_layer in pyramid_layers:
                img_layer = img_layer.astype(img_data_type)
                pyramid_5d.append(_expand_dims(img_layer, color_type))

            write_multiscale(
                pyramid_5d,
                channel_group,
                axes=axes,
                coordinate_transformations=coordinate_transformations,
                compressor=compressor,
            )

    logger.info(
        f"FINISH WRITING OME-ZARR WITH {no_of_channels} CHANNELS AND "
        f"{levels} PYRAMIDAL LEVELS"
        )
    return zarr_path



def write_pyramid_omezarr_streaming(
    delayed_img,
    levels,
    outdir,
    file_name,
    img_data_type,
    color_type,
    compress="default",
    use_queue=True,
    ome=None,
    chunk_size=(1, 1, 1, 256, 256)
):
    """
    Write a standard OME-Zarr pyramid (all channels in one 5D array)
    using a producer-consumer queue for speed.

    The root group contains arrays "0", "1", ... for each resolution level,
    each with shape (1, n_channels, 1, H, W). The multiscales metadata is
    stored in the root .zattrs.

    Parameters match write_pyramid_omezarr, plus optional `ome` (XML or
    ome_types object) and `chunk_size` for the Zarr arrays.
    """
    if color_type != "grayscale":
        raise NotImplementedError(
            "Streaming writer currently supports only 'grayscale' channels."
        )
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    zarr_path = outdir / file_name
    if not str(zarr_path).endswith(".zarr"):
        zarr_path = outdir / (file_name + ".zarr")

    root = zarr.open_group(str(zarr_path), mode="w")
    codec =  _get_zarr_v3_codec(compress)
    n_channels = len(delayed_img)

    # Optional OME metadata at root
    if ome is not None:
        ome_xml = ome if isinstance(ome, str) else ome.to_xml()
        root.attrs["omero"] = {"metadata": ome_xml, "version": "0.4"}

    # Determine level 0 dimensions by computing the first channel.
    # This will be recomputed in the producer; if you want to avoid that,
    # you can pre-compute and skip it in the producer (see note below).
    first_channel = delayed_img[0].compute()
    h0, w0 = first_channel.shape
    dims_schedule = [
        (int(np.rint(h0 / (2**i))), int(np.rint(w0 / (2**i))))
        for i in range(levels)
    ]

    # Pre-allocate arrays for each level at the root
    level_arrays = []
    for i, (h, w) in enumerate(dims_schedule):
        kwargs = {
            "shape": (1, n_channels, 1, h, w),
            "chunks": chunk_size,
            "dtype": img_data_type,
        }
        if codec is not None:
            # Try 'compressor' first; if your zarr version expects
            # 'compressors' or another name, adjust accordingly.
            kwargs["compressors"] = [codec]
        arr = root.create_dataset(str(i), **kwargs)
        level_arrays.append(arr)

    if use_queue:
        q = queue.Queue(maxsize=1)
        producer_thread = threading.Thread(
            target=_pyramid_producer,
            args=(delayed_img, levels, color_type, q),
            daemon=True
        )
        producer_thread.start()

        current_channel_idx = 0   # will be updated by 'channel_start'

        while True:
            item = q.get()
            msg_type = item[0]

            if msg_type == 'stop':
                break
            elif msg_type == 'error':
                raise item[1]
            elif msg_type == 'channel_start':
                current_channel_idx = item[1]
                logger.info(
                    f"WRITING CHANNEL: {current_channel_idx}/{n_channels} "
                    f"(PYRAMIDAL LEVELS:{levels})"
                )
            else:  # 'data'
                _, layer_index, img_layer = item
                img_layer = img_layer.astype(img_data_type)
                # Write into the correct slice: (1, channel_idx-1, 1, :, :)
                level_arrays[layer_index][
                    0, current_channel_idx - 1, 0, :, :
                ] = img_layer

        producer_thread.join(timeout=0.1)

    else:
        # Sequential fallback (no threading)
        for channel_idx, trf_channel in enumerate(delayed_img, start=1):
            logger.info(f"Writing channel {channel_idx}/{n_channels}")
            img_arr = trf_channel.compute()
            for layer_idx, img_layer in enumerate(
                pyramid_generator(img_arr, levels, color_type)
            ):
                img_layer = img_layer.astype(img_data_type)
                level_arrays[layer_idx][
                    0, channel_idx - 1, 0, :, :
                ] = img_layer

    # Manually write the OME-Zarr multiscales metadata
    axes = [
        {"name": "t", "type": "time", "unit": "millisecond"},
        {"name": "c", "type": "channel"},
        {"name": "z", "type": "space", "unit": "micrometer"},
        {"name": "y", "type": "space", "unit": "micrometer"},
        {"name": "x", "type": "space", "unit": "micrometer"},
    ]
    datasets = [
        {
            "path": str(level_idx),
            "coordinateTransformations": [
                {
                    "type": "scale",
                    "scale": [1.0, 1.0, 1.0, 2**level_idx, 2**level_idx]
                }
            ],
        }
        for level_idx in range(levels)
    ]
    root.attrs["multiscales"] = [
        {
            "version": "0.4",
            "name": file_name,
            "axes": axes,
            "datasets": datasets,
        }
    ]

    logger.info(
        f"FINISH WRITING OME-ZARR WITH {n_channels} CHANNELS AND "
        f"{levels} PYRAMIDAL LEVELS"
    )
    return zarr_path