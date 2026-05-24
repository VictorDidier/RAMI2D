import tifffile as tifff
from types import GeneratorType
from skimage.transform import pyramid_gaussian

def extract_levels_from_tiff(path,ch,levs):
    with tifff.TiffFile(path) as tif:
        for l in range(levs):
            yield tif.series[0].levels[l].pages[ch].asarray()

def generate_tiff_pyramid(img_instances,
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



    #
    types=[]
    for element in img_instances:

        if isinstance(element, GeneratorType):

            types.append("generator")

        elif isinstance(element, Path):

            types.append("path")

        else:

            types.append("other")

    #
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