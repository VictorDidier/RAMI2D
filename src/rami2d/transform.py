#public libraries
from pathlib import Path
import argparse
import itk
import tifffile as tifff
import tracemalloc
import time
import pandas as pd
from loguru import logger
#local scripts
from .utils_reg import apply_transform_delayed
from .tiff_writer import write_pyramid
from .processing_tools import ImageFileGateway
from . import ome_writer
from .version import __version__


# CLI

def get_args():
    parser=argparse.ArgumentParser()

    parser.add_argument('-i',
                        '--image_file_path',
                        required=True,
                        type=Path,
                        help='absolute path to the image'
                        )
    
    parser.add_argument('-mpp',
                        '--image_microns_per_pixel',
                        required=True,
                        type=float,
                        help='pixel size of the image in microns'
                        )
    
    parser.add_argument('-tdir',
                        '--transformations_dir',
                        required=True,
                        type=Path,
                        help='absolute path to directory containing the transformation files'
                        )
    
    parser.add_argument('-o',
                        '--output_dir',
                        required=True,
                        type=Path,
                        help='absolute path to the output directory'
                        )
    
    parser.add_argument('-labels',
                    '--is_image_labels',
                    action='store_true',
                    help="""Use this argument if the input image exclusively contains labeled masks, e.g. 
                    segmentation masks, binary masks or ROI annotations. This arguments sets up the 
                    right interpolation method (nearest neighbors) for such images during the transformation.
                    """
                    )
    

    parser.add_argument('-fn',
                        '--file_name_suffix',
                        required=False,
                        type=str,
                        default="transformed",
                        help='suffix to be appended to the registered output image'
                        )

    parser.add_argument('-pl',
                        '--pyramid_levels',
                        required=False,
                        type=int,
                        default=8,
                        help="number of pyramid levels in the registered output image"
                        )
    
    parser.add_argument('-comp',
                        '--compression_algorithm',
                        required=False,
                        type=str,
                        default="default",
                        help="""Default behaviour of this argument is to compress the output registered image with
                        "lzw" or "jpeg2000" if image is grayscale or RGB correspondingly.  If no compression is required
                        set this argument to "None". In case you want to try other compression algorithms, this argument accepts
                        any option available in the tifffile python package (https://pypi.org/project/tifffile/) formated as a lower case string,
                        e.g. "jpeg","zlib", etc.
                        """
                        )
    
    parser.add_argument('-m',
                        '--markers_file',
                        required=False,
                        type=Path,
                        help="""a .csv file with a column named marker_name that contains the names
                        of the channels in the same order that they appear in the input image
                        """
                        )
    
    parser.add_argument('-v',
                    '--version',
                    dest='version',
                    action='version',
                    version=f"{__version__}"
                    )
    
    args=parser.parse_args()
    return args
    

def main():
    tracemalloc.start()
    st = time.time()
    # Get cli arguments 
    args=get_args()
    image_path=args.image_file_path
    is_labels=args.is_image_labels
    mpp=args.image_microns_per_pixel
    trf_dir=args.transformations_dir
    output_dir=args.output_dir
    suffix=args.file_name_suffix
    levels=args.pyramid_levels
    compression_method=args.compression_algorithm
    markers=args.markers_file
    # validate transforsmations_dir
    if not trf_dir.exists():
        raise Exception(f"The transformations directory {trf_dir} does not exist")
    elif not list(trf_dir.glob("*.txt")):
        raise Exception(f"The transformations directory {trf_dir} does not contain any .txt transformation files")

    # Read transformation files
    logger.info(f"FETCHING TRANSFORMS FROM: \n {trf_dir}")
    trf_files=sorted(list(trf_dir.glob("*.txt")))
    transformation_map=itk.ParameterObject.New()
    for f in trf_files:
        transformation_map.AddParameterFile(str(f))
    out_mpp=float(transformation_map.GetParameter(0,"Spacing")[0])
    # Read input image
    input_image=ImageFileGateway(image_path,mpp)
    img_props=input_image.props

    # Apply transformations
    image_transformed=apply_transform_delayed(input_image,transformation_map,is_label=is_labels)

    # Write transformed image accordingly

    if is_labels:
        out_file_name=f'{ (image_path.stem).split(".ome")[0] }_{suffix}.tif'
        pyramid_levels=1
        compression_method="None"
    else:
        out_file_name=f'{ (image_path.stem).split(".ome")[0] }_{suffix}.ome.tif'
        #pyramid_levels=img_props["levels"]
        pyramid_levels=levels

    logger.info(f"""COMMENCING TRANSFORMATION AND WRITING OF MOVING IMAGE ON:\n
        {output_dir / out_file_name}\n 
        WITH RESOLUTION OF: {out_mpp} MICRONS""")
    
    out_file_path=write_pyramid(
                    image_transformed,
                    pyramid_levels,
                    output_dir,
                    out_file_name,
                    img_props["data_type"],
                    img_props["color_type"],
                    compression_method
                    )
    
    if not is_labels:
        props_out=ImageFileGateway(out_file_path,out_mpp).props
        if markers:
            channel_names=pd.read_csv(markers)["marker_name"].tolist()
        else:
            channel_names=[f"Channel-{ch}" for ch in range(props_out["channels"])]
        ome_xml=ome_writer.create_ome(channel_names,props_out,f"rami2d-{__version__}")
        tifff.tiffcomment(out_file_path, ome_xml.encode("utf-8"))
    print("Memory peak:",((10**(-9))*tracemalloc.get_traced_memory()[1],"GB"))
    rt = time.time() - st
    tracemalloc.stop()
    print(f"Script finished in {rt // 60:.0f}m {rt % 60:.0f}s")


if __name__ == '__main__':
    main()