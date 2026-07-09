import tifffile as tifff
from types import GeneratorType
from pathlib import Path
from skimage.util import img_as_float32
from skimage.exposure import rescale_intensity
from skimage.transform import resize,rescale
import dask.array as da
from dask_image.ndfilters import gaussian_filter
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
                    img_file_object,
                    transformation_map,
                    levels,
                    outdir,
                    file_name,
                    img_data_type,
                    color_type,
                    compress="default"
                    ):

    outdir.mkdir(parents=True, exist_ok=True)
    out_file_path= outdir / file_name
    tiff_compression_opts=[element.name.lower() for element in list(tifff.COMPRESSION) if not element.name.lower()=="none"]

    if compress=="default":
        output_file_compression="jpeg2000" if color_type in ("RGB","RGBA") else "lzw"
    elif compress=="None":
        output_file_compression=None
    elif compress in tiff_compression_opts:
        output_file_compression=compress
    else:
        raise ValueError(f"Compression value {compress} not supported")

    color_interpretation=img_file_object.props["color_type"]
    if color_interpretation=="grayscale":
        no_of_ch=img_file_object.props["channels"]
    elif color_interpretation in ["RGB","RGBA"]:
        no_of_ch=1#only single page RGB images are accepted

    sublayers=levels-1

    with tifff.TiffWriter(out_file_path, ome=False, bigtiff=True) as tif:

        for ch_index in range(no_of_ch):

            pyramid_layers=pyramid_generator(
                                            apply_transform(img_file_object,transformation_map,ch_index), 
                                            levels,
                                            color_type=color_interpretation
                                            )
            
            for layer_index,img_layer in enumerate(pyramid_layers):

                tif.write(
                        img_layer.astype(img_data_type),
                        description="",
                        subfiletype=0 if layer_index==0 else 1,
                        subifds=sublayers if layer_index==0 else None,
                        metadata=False,  # IMPORTANT: do not write tifffile metadata here to allow adding ome later
                        tile=(256, 256),
                        photometric="rgb" if color_type in ("RGB","RGBA") else "minisblack",
                        compression=output_file_compression
                        )

    return out_file_path

def write_pyramid2(delayed_img,
                    levels,
                    outdir,
                    file_name,
                    img_data_type,
                    color_type,
                    compress="default"
                    ):

    outdir.mkdir(parents=True, exist_ok=True)
    out_file_path= outdir / file_name
    tiff_compression_opts=[element.name.lower() for element in list(tifff.COMPRESSION) if not element.name.lower()=="none"]

    if compress=="default":
        output_file_compression="jpeg2000" if color_type in ("RGB","RGBA") else "lzw"
    elif compress=="None":
        output_file_compression=None
    elif compress in tiff_compression_opts:
        output_file_compression=compress
    else:
        raise ValueError(f"Compression value {compress} not supported")

    sublayers=levels-1

    with tifff.TiffWriter(out_file_path, ome=False, bigtiff=True) as tif:

        for trf_channel in delayed_img:

            pyramid_layers=pyramid_generator(trf_channel.compute(),levels,color_type)
            
            for layer_index,img_layer in enumerate(pyramid_layers):

                tif.write(
                        img_layer.astype(img_data_type),
                        description="",
                        subfiletype=0 if layer_index==0 else 1,
                        subifds=sublayers if layer_index==0 else None,
                        metadata=False,  # IMPORTANT: do not write tifffile metadata here to allow adding ome later
                        tile=(256, 256),
                        photometric="rgb" if color_type in ("RGB","RGBA") else "minisblack",
                        compression=output_file_compression
                        )

    return out_file_path


def write_pyramid_general(img_instances,
                    levels,
                    outdir,
                    file_name,
                    img_data_type,
                    color_type,
                    compress="default"
                    ):

    outdir.mkdir(parents=True, exist_ok=True)
    out_file_path= outdir / file_name

    validate_compression(compress)

    types=[]
    for element in img_instances:
        if isinstance(element, GeneratorType):
            types.append("generator")
        elif isinstance(element, Path):
            types.append("path")
        else:
            types.append("other")

    pyramid_levels=[]
    for path,element in zip(img_instances,types):

        if element=="path":

            pyramid_levels.append( is_pyramid(path)[1] )

        else:

            pyramid_levels.append(1)

    #
    unfolded_instances=[]
    for INST,TYPE,LEVL in zip(img_instances,types,pyramid_levels):

        if TYPE=="path":
            deficit=levels-LEVL
            aux_path=INST
            with tifff.TiffFile(aux_path) as tif:
                no_channels=len(tif.pages)

            for ch_idx in range(no_channels):
                if (deficit==0 or deficit<0):

                    unfolded_instances.append(extract_levels_from_tiff(aux_path,ch_idx,levels))

                elif deficit>0:
                    aux_1=(tifff.imread(aux_path,series=0,key=ch_idx,level=L) for L in range(LEVL) )
                    aux_2=pyramid_gaussian( tifff.imread(aux_path,series=0,key=ch_idx,level=LEVL-1), max_layer=deficit, preserve_range=True,order=1,sigma=1)
                    next(aux_2)
                    unfolded_instances.append(itertools.chain(aux_1,aux_2))

        if TYPE=="generator":
            for channel in INST:
                unfolded_instances.append( pyramid_gaussian( channel,
                                                            max_layer=levels-1,
                                                            preserve_range=True,
                                                            order=1,
                                                            sigma=1,
                                                            channel_axis=2 if color_type in ("RGB","RGBA") else None
                                                            )
                                          )

    sublayers=levels-1
    with tifff.TiffWriter(out_file_path, ome=False, bigtiff=True) as tif:
        #write first the original resolution image,i.e. first layer
        for img_generator in unfolded_instances:
            for layer,img_layer in enumerate(img_generator):
                tif.write(
                        img_layer.astype(img_data_type),
                        description="",
                        subfiletype=0 if layer==0 else 1,
                        subifds=sublayers if layer==0 else None,
                        metadata=False,  # IMPORTANT: do not write tifffile metadata here to allow adding ome later
                        tile=(256, 256),
                        photometric="rgb" if color_type in ("RGB","RGBA") else "minisblack",
                        compression=output_file_compression
                        )

    return out_file_path