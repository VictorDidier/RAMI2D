#public libraries
from pathlib import Path
import pandas as pd
import tifffile as tifff
import numpy as np
from skimage.util import img_as_float32
import tracemalloc
import time
import argparse
import itk
from loguru import logger
#local scripts
from . import utils_reg
from . import ome_writer
from . import initial_align
from .processing_tools import ImageFileGateway
from .tiff_writer import write_pyramid,write_pyramid_omezarr,write_pyramid_omezarr_streaming
from .version import __version__



#CLI
def get_args():
    parser=argparse.ArgumentParser()
    parser.add_argument('-fix',
                        '--fixed_img',
                        required=True,
                        type=Path,
                        help='absolute path of the image stack contaninig the fix image '
                        )

    parser.add_argument('-mov',
                        '--moving_img',
                        required=True,
                        type=Path,
                        help='absolute path of the image stack contaninig the moving image'
                        )

    parser.add_argument('-ifix',
                    '--fixed_reference_channel_index',
                    required=True,
                    help="0-based index of the channel to be used for the registration in the fixed image stack"
                    )

    parser.add_argument('-imov',
                    '--moving_reference_channel_index',
                    required=True,
                    help="0-based index of the channel to be used for the registration in the moving image stack"
                    )

    parser.add_argument('-o',
                        '--outdir',
                        required=True,
                        type=Path,
                        help='absolute path of the directory where the output .csv file will be written'
                        )

    parser.add_argument('-mpp-fix',
                        '--fix_microns_per_pixel',
                        required=True,
                        type=float,
                        help='pixel size of the fixed image in microns'
                        )

    parser.add_argument('-mpp-mov',
                        '--mov_microns_per_pixel',
                        required=True,
                        type=float,
                        help='pixel size of the moving image in microns'
                        )

    parser.add_argument('-mpp-key',
                        '--keypoints_microns_per_pixel',
                        required=False,
                        type=float,
                        help="""
                        The fixed and moving images will be resized so their pixel size matches this value.
                        These resized images will be used to find keypoints that help estimating the initial alignment.
                        """
                        )

    parser.add_argument('-mpp-reg',
                        '--registration_microns_per_pixel',
                        required=True,
                        type=float,
                        help="""The fixed and moving images will be resized so their pixel size matches this value.
                        The resized images will be used to calculate the registration parameters using the selected
                        registration scheme.
                        """
                        )

    parser.add_argument('-fn',
                        '--file_name_suffix',
                        required=False,
                        type=str,
                        default="registered",
                        help='suffix to be appended to the registered output image'
                        )

    parser.add_argument('-m',
                        '--markers_file',
                        required=False,
                        type=Path,
                        help="""a .csv file with a column named marker_name that contains the names
                        of the channels in the same order that they appear in the moving image input
                        """
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


    parser.add_argument('-rsc',
                        '--registration_scheme',
                        required=False,
                        type=int,
                        default=1,
                        choices=[1,2,3],
                        help="""1: rigid,
                                2: rigid->affine,
                                3: rigid->affine->bsplines
                            """
                        )

    parser.add_argument('-a',
                    '--initial_alignment',
                    action='store_true',
                    help="""Use this flag to estimate via keypoints match an initial alignment between
                    fixed and moving images. Use this when fix and moving images that are highly misaligned
                    respect to each other, e.g. rotated by large angles or have different fields of view.
                    """
                    )
    
    parser.add_argument('-fl',
                    '--flip_moving_image',
                    action='store_true',
                    help="""Flip moving image horizontally. Use this
                    argument if the orientation of your fixed and 
                    moving images are mirrored,i.e. they cannot be 
                    overlapped by a translation and/or rotation.
                    """
                    )
    
    parser.add_argument('-masked',
                    '--masked_foreground_sampling',
                    action='store_true',
                    help="""Registration is calculated with random samples of the image foreground instead of 
                    random samples from the whole image area. This feature is ONLY recommended in images with extremely 
                    sparse foreground content.
                    """
                    )
    
    parser.add_argument('-gs',
                    '--grid_spacing_um',
                    required=False,
                    nargs=2,
                    default=[1000, 1000],
                    type=float,
                    help="""Two positive float numbers that represent the grid spacing
                    to be used in the bsplines registration.  This argument has no effect if
                    bsplines is not used. To be consistent with other arguments
                    this numbers should be given in micrometers.  !!!Be carefule with the selection
                    of values here, too small will produce very distorted images, too big and effect of
                    bsplines will be hardly visible.  Choose values that are of the order of your
                    expected deformation.
                    """
                    )

    parser.add_argument('-test',
                    '--test_mode',
                    action='store_true',
                    help="""Use this flag to skip writting the full resolution image.
                    This mode is useful with big images that do not fit in RAM.  You can activate this mode and
                    check the results of the registration on the downsampled images by going into the qc_folder created in the output folder.
                    """
                    )
    
    parser.add_argument('-v',
                    '--version',
                    action='version',
                    version=f"{__version__}"
                    )


    args=parser.parse_args()
    return args

#HELPERS
def validate_channel_args(args):
    channel_args={"fixed":args.fixed_reference_channel_index,
                  "moving":args.moving_reference_channel_index}
    output=[]
    for key,val in channel_args.items():
        try:
            output.append(int(val))
        except ValueError:
            if val in ["h","e","d"]:
                output.append(val)
            else:
                raise ValueError(f"""
                        Channel indices of {key} image expect an integer or a string
                        from the list ["h","e","d"]. Verify your inputs.
                        """
                        )
    fix_ch,mov_ch=output[0],output[1]
    return fix_ch,mov_ch

def validate_align_args(args):
    if args.initial_alignment:
        if args.keypoints_microns_per_pixel:
            pass
        else:
            raise ValueError("""Initial alignment (-a) was setup but no mpp-key argument was given.
                             Please provide the image resolution (mpp-key )
                             at which you want the keypoints to be searched.
                             """
                             )
    else:
        pass

def make_outdirs(out_root_dir):
    qc_dir=out_root_dir / "qc"
    outdirs={"root":out_root_dir,
             "qc":qc_dir,
             "keypoints":qc_dir /"keypoints",
             "refchns":qc_dir / "refchns",
             "transforms":qc_dir / "refchns" /"transforms",
             "fullres_trf":qc_dir / "fullres_trf"
            }
    for _,dirpath in outdirs.items():
        dirpath.mkdir(parents=True,exist_ok=True)
    return outdirs



def main():
    tracemalloc.start()
    st = time.time()
    #Collect arguments
    args = get_args()
    fixed_img_path=args.fixed_img
    moving_img_path=args.moving_img
    output_dir=args.outdir
    mpp_fix=args.fix_microns_per_pixel
    mpp_mov=args.mov_microns_per_pixel
    suffix=args.file_name_suffix
    markers=args.markers_file
    fixed_ch=args.fixed_reference_channel_index
    moving_ch=args.moving_reference_channel_index
    fixed_ch,moving_ch=validate_channel_args(args)
    levels=args.pyramid_levels
    key_mpp=args.keypoints_microns_per_pixel
    reg_mpp=args.registration_microns_per_pixel
    compression_method=args.compression_algorithm
    reg_scheme=args.registration_scheme
    apply_initial_alignment=args.initial_alignment
    grid_spacing=args.grid_spacing_um
    test_mode=args.test_mode
    flip_horizontally=args.flip_moving_image
    masked_sampling=args.masked_foreground_sampling

    validate_align_args(args)
    #Define and create qc and/or output directories
    outdirs=make_outdirs(output_dir)
    if apply_initial_alignment or flip_horizontally:
        init_trf_dir=outdirs["transforms"] / "00_initial"
        init_trf_dir.mkdir(parents=True,exist_ok=True)

    #Extract image properties,i.e. pyramidal, mpp,dimensions, etc.
    Fix=ImageFileGateway(fixed_img_path,mpp_fix)
    Mov=ImageFileGateway(moving_img_path,mpp_mov)

    fixed_props=Fix.props
    moving_props=Mov.props

    if moving_props["pyramid"]:
        out_levels=moving_props["levels"]
    else:
        out_levels=levels

    #Extract channels of fixed image and moving image channels to be used for registration.
    #Resize both fixed and moving image to have the same mpp
    logger.info("COMMENCING RESIZING OF REFERENCE CHANNELS FOR FIXED AND MOVING IMAGES")
    logger.info(f"FIXED IMAGE (REF-CH {fixed_ch}):\n {fixed_img_path}")
    logger.info(f"MOVING IMAGE (REF-CH {moving_ch}):\n {moving_img_path}")
    reg_fixed_img,reg_moving_img=utils_reg.resize_and_extract_channels(Fix,Mov,fixed_ch,moving_ch,reg_mpp)
    #Save reference images in qc_dir for reference
    tifff.imwrite(outdirs["refchns"]/f"fixed_ch-{fixed_ch}.tif", reg_fixed_img,photometric="minisblack")
    tifff.imwrite(outdirs["refchns"]/f"moving_ch-{moving_ch}.tif",reg_moving_img,photometric="minisblack")

    #Calculate initial alignment
    if apply_initial_alignment:
        logger.info(f"COMMENCING SEARCH/VALIDATION OF KEYPOINTS FOR INITIAL ALIGNMENT AT {key_mpp} MICRONS RESOLUTION")
        key_fixed_img,key_moving_img=utils_reg.resize_and_extract_channels(Fix,Mov,fixed_ch,moving_ch,key_mpp)
        #QC outputs
        tifff.imwrite(outdirs["keypoints"]/"fixed_keypoints.tif",key_fixed_img,photometric="minisblack")
        if flip_horizontally:
            tifff.imwrite(outdirs["keypoints"]/"moving_keypoints.tif",np.flip(key_moving_img,axis=1),photometric="minisblack")
        else:
            tifff.imwrite(outdirs["keypoints"]/"moving_keypoints.tif",key_moving_img,photometric="minisblack")
        
        height,width=reg_fixed_img.shape
        init_trf=initial_align.get_initial_trf(key_fixed_img,
                                               key_moving_img,
                                               key_mpp,
                                               outdirs["keypoints"],#directory to save ransac_matches.png
                                               output_dict={"mpp":reg_mpp,"xy_dims":[width,height]},
                                               fliph_mov=flip_horizontally
                                               )

    elif flip_horizontally:
        height,width=reg_moving_img.shape
        init_trf=utils_reg.generate_flip_transform([width,height],reg_mpp)
    
    else:
        init_trf=None


    if init_trf:
        mov_itk=itk.GetImageFromArray(img_as_float32(reg_moving_img))
        mov_itk.SetSpacing([reg_mpp,reg_mpp])
        reg_moving_img=itk.transformix_filter(mov_itk,init_trf,log_to_console=False)
        #Save results for qc
        utils_reg.save_init_trf_maps(init_trf,init_trf_dir)
        tifff.imwrite(init_trf_dir/"moving_init_aligned.tif",reg_moving_img,photometric="minisblack")

    #Extract transforms from registering with registration scheme (rigid,affine,bsplines).
    logger.info(f"COMMENCING REGISTRATION OF REFERENCE CHANNELS AT {reg_mpp} MICRONS RESOLUTION")
    transformations_map=utils_reg.register_references(
                        reg_fixed_img,
                        reg_moving_img,
                        reg_mpp,
                        outdirs["transforms"],
                        reg_scheme,
                        apply_initial_alignment,
                        grid_spacing,
                        masked_sampling
                        )
    # Adjust initial transform according to final dimensions and pixel size
    output_img_size=(fixed_props["size_x"],fixed_props["size_y"])
    out_mpp=mpp_fix
    transformations_map=utils_reg.create_final_trf_map(transformations_map,
                                             output_img_size,
                                             out_mpp,
                                             init_trf,
                                             init_map_conformed=True
                                             )
    # Write all final transformations into the fullres_trf folder
    no_of_trf_maps=transformations_map.GetNumberOfParameterMaps()
    logger.info(f"WRITING TRANSFORMATION FILES ON DIRECTORY:\n {outdirs['fullres_trf']}")
    transformations_map.WriteParameterFile(transformations_map.GetParameterMaps(),
                                           [str(outdirs["fullres_trf"]/f"trf_{i:02d}.txt") for i \
                                            in range(no_of_trf_maps)]
                                           )

    #Apply transformations to the moving image and upscale to the dimensions of the fixed image

    if not test_mode:
        out_file_name=f'{ (moving_img_path.stem).split(".ome")[0] }_{suffix}.tif'
        logger.info(f"""COMMENCING TRANSFORMATION AND WRITING OF MOVING IMAGE ON:\n 
        {output_dir / out_file_name}\n 
        WITH RESOLUTION OF: {mpp_fix} MICRONS""")

        registered_mov=utils_reg.apply_transform_delayed(Mov,transformations_map)
        out_img_path=write_pyramid(
                    registered_mov,
                    out_levels,
                    output_dir,
                    out_file_name,
                    moving_props["data_type"],
                    moving_props["color_type"],
                    compression_method
                    )
        #Update moving image props after registration
        """
        moving_props_out=ImageFileGateway(out_img_path,out_mpp).props
        if markers:
            channel_names=pd.read_csv(markers)["marker_name"].tolist()
        else:
            channel_names=[f"Channel-{ch}" for ch in range(moving_props_out["channels"])]
        #Write metadata in OME format into the pyramidal file
        ome_xml=ome_writer.create_ome(channel_names,moving_props_out,f"rami2d-{__version__}")
        tifff.tiffcomment(out_img_path, ome_xml.encode("utf-8"))
        """
    
    print("Memory peak:",((10**(-9))*tracemalloc.get_traced_memory()[1],"GB"))
    rt = time.time() - st
    tracemalloc.stop()
    print(f"Script finished in {rt // 60:.0f}m {rt % 60:.0f}s")


if __name__ == '__main__':
    main()