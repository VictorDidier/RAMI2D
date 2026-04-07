#public libraries
from pathlib import Path
import itertools
import pandas as pd
from skimage.transform import pyramid_gaussian
import tifffile as tifff
import numpy as np
from skimage.util import img_as_float32
from types import GeneratorType
import tracemalloc
import time
import argparse
import os
import itk
import shutil
import warnings
#local scripts
from . import ome_writer
from . import initial_align
from . import processing_tools as prt
from .processing_tools import ImageFileGateway



#CLI
def get_args():
    parser=argparse.ArgumentParser()
    parser.add_argument('-fix',
                        '--fixed_img',
                        required=True,
                        type=Path,
                        help='absolute path of the image stack (.tif) contaninig the fix image '
                        )

    parser.add_argument('-mov',
                        '--moving_img',
                        required=True,
                        type=Path,
                        help='absolute path of the image stack (.tif) contaninig the moving image'
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
                    help="""Use this flag to estimate an initial alignment between
                    fixed and moving images that are highly misaligned respect to each other,
                    e.g. rotated by large angles or have different xy dimensions.
                    """
                    )
    
    parser.add_argument('-fl',
                    '--flip_moving_image',
                    action='store_true',
                    help="""Flip moving image horizontally. Use this
                    argument if the orientation of your fixed and 
                    moving images are mirrored,i.e. cannot be 
                    overlapped by a translation and rotation.
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


    args=parser.parse_args()
    return args

#HELPERS

def register_references(fixed,moving,mpp,out_trf_dir,scheme,init_align,grid_spacing):
    #Define variables
    scheme_opts={1:["01_rigid"],
            2:["01_rigid","02_affine"],
            3:["01_rigid","02_affine","03_bspline"]
            }
    transform_scheme=scheme_opts[scheme]
    global_trf_map=itk.ParameterObject.New()
    workdir=Path( os.path.dirname(__file__) )
    registration_maps=sorted( (workdir / "maps" / "registrations").glob("*.txt") )

    qc_trf_out=[]

    for element in transform_scheme:
        aux=out_trf_dir / element
        aux.mkdir(exist_ok=True,parents=True)
        qc_trf_out.append(aux)

    fix_itk=itk.GetImageFromArray(img_as_float32(fixed))
    fix_itk.SetSpacing([mpp,mpp])
    mov_itk=itk.GetImageFromArray(img_as_float32(moving))
    mov_itk.SetSpacing([mpp,mpp])
    #fixed_mask=prt.get_foreground_mask(fixed,mpp)
    #Initial transformation to align the principal axis
    #mov_updated below is already an itk image with the mpp spacing
    loop_idx=0
    for Reg,Out in zip(registration_maps,qc_trf_out):
        reg_map=itk.ParameterObject.New()
        reg_map.AddParameterFile(str(Reg))
        if loop_idx==0:
            reg_map.SetParameter(0,
                                 "AutomaticTransformInitialization",
                                 ["false" if init_align else "true"]
                                )
        if scheme==3:
            reg_map.SetParameter(0,
                                 "FinalGridSpacingInPhysicalUnits",
                                 [str(val) for val in grid_spacing ]
                                )

        mov_itk,result_trf_params = itk.elastix_registration_method(
                                                                    fix_itk,
                                                                    mov_itk,
                                                                    parameter_object=reg_map,
                                                                    fixed_mask=None,
                                                                    output_directory=str(Out),
                                                                    log_file_name="log.txt",
                                                                    log_to_console=False
                                                                    )

        global_trf_map.AddParameterMap(result_trf_params.GetParameterMap(0))
        loop_idx+=1

    return global_trf_map

def apply_transform(img_object,transform_map,mpp_full,in_mpp=False,is_label=False):

    if isinstance(img_object,Path) or isinstance(img_object,str):
        img_object=ImageFileGateway(img_object,in_mpp)
    else:
        pass

    if is_label:
        for n in range(transform_map.GetNumberOfParameterMaps()):
            transform_map.SetParameter(n,"FinalBSplineInterpolationOrder", "0")

    color_interpretation=img_object.props["color_type"]
    if color_interpretation=="grayscale":
        no_of_ch=img_object.props["channels"]
    elif color_interpretation in ["RGB","RGBA"]:
        no_of_ch=1#for the moment all color images have to be converted to RGB

    for ch_index in range(no_of_ch):
        if color_interpretation=="grayscale":
            result=itk.GetImageFromArray( img_object.resize(mpp_full,ch=ch_index))
            result.SetSpacing([mpp_full,mpp_full])
            result=itk.transformix_filter(result,transform_map,log_to_console=False)
            yield itk.GetArrayFromImage( result )
        elif color_interpretation in ["RGB","RGBA"] :
            #result=itk.GetImageFromArray( img_object.resize(mpp_full)[:,:,ch_index])
            rgb_input=img_object.resize(mpp_full)
            rgb_output=[]
            for color_index in range(3):
                #result=itk.GetImageFromArray(rgb_input[:,:,color_index])
                result=itk.GetImageFromArray(np.take(rgb_input,color_index,axis=img_object.props["ch_idx"]))
                result.SetSpacing([mpp_full,mpp_full])
                result=itk.transformix_filter(result,transform_map,log_to_console=False)
                rgb_output.append(itk.GetArrayFromImage( result ))
            yield np.stack(rgb_output, axis=2)


def extract_levels_from_tiff(path,ch,levs):
    with tifff.TiffFile(path) as tif:
        for l in range(levs):
            yield tif.series[0].levels[l].pages[ch].asarray()

def create_pyramid(img_instances,
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

def create_final_trf_map(trf,output_size,out_mpp,init_map=None):
    #Edit initial transformation map
    final_transform_map=itk.ParameterObject.New()
    trf_maps=[]
    if init_map:
        for n in range(init_map.GetNumberOfParameterMaps()):
            init_map.SetParameter(n,"Size", [str(val) for val in output_size ])
            init_map.SetParameter(n,"Spacing",[str(out_mpp),str(out_mpp)])
            trf_maps.append(init_map.GetParameterMap(n))

    for n in range(trf.GetNumberOfParameterMaps()):
        trf.SetParameter(n,"Size", [str(val) for val in output_size ])
        trf.SetParameter(n,"Spacing",[str(out_mpp),str(out_mpp)])
        trf_maps.append(trf.GetParameterMap(n))

    for map in reversed(trf_maps):
        final_transform_map.AddParameterMap(map)

    return final_transform_map

def save_init_trf_maps(trf_object,outdir):
    outdir.mkdir(parents=True,exist_ok=True)
    for index in range(trf_object.GetNumberOfParameterMaps()):
        out_file_path=outdir/ f"{index:02d}_TransformParameters.0.txt"
        parameter_map = trf_object.GetParameterMap(index)
        trf_object.WriteParameterFile(parameter_map, str(out_file_path) )



def resize_and_extract_channels(fix,mov,fix_ch,mov_ch,target_mpp):
    #fix,mov are a ImageFileGateway class
    hed2index={"h":0,"e":1,"d":3}
    hed2name={"h":"Hematoxylin","e":"Eosin","d":"DAB"}
    input_imgs=[fix,mov]
    input_chs=[fix_ch,mov_ch]
    output_imgs=[]
    for ch,im in zip(input_chs,input_imgs):
        if im.props["color_type"] in ("RGB","RGBA"):
            #constrained to single page RGB images
            pre_img=im.resize(target_mpp)
            if isinstance(ch,int):
                pre_img=np.take(pre_img,ch,axis=im.props["ch_idx"])
            elif isinstance(ch,str):
                print(f"extracting {hed2name[ch]} from {im.file}")
                pre_img=prt.get_hed_channels(pre_img,color_axis=im.props["ch_idx"])
                pre_img=pre_img[:,:,hed2index[ch]]
            output_imgs.append(pre_img)

        elif im.props["color_type"]=="grayscale":
            if isinstance(ch,int):
                output_imgs.append(im.resize(target_mpp,ch=ch))
            elif isinstance(ch,str):
                warnings.warn(f"""Warning!: You requested the extraction of {hed2name[ch]}
                                from {im.file}, this is only possible for an RGB image
                                but the photometric value of your image file indicates that your image was saved as grayscale.
                                """
                                  )
                if im.props["channels"]>=3:
                    warnings.warn(f"Warning!:The first 3 channels of your image will be interpreted as RGB channels")
                    pre_img=im.resize(target_mpp,ch=[0,1,2])
                    pre_img=prt.get_hed_channels(pre_img,color_axis=im.props["ch_idx"])
                    pre_img=pre_img[:,:,hed2index[ch]]
                    output_imgs.append(pre_img)
                else:
                    raise ValueError(f"Cannot extract {hed2name[ch]} channel for a grayscale image with less than 3 channels")

    for n,im in enumerate(output_imgs):
        rsm,contrast=prt.measure_contrast(im)
        #if rsm<0.1:
        output_imgs[n]=prt.enhance_contrast(im)
        rsm,contrast=prt.measure_contrast(output_imgs[n])
    fix_resized=output_imgs[0]
    mov_resized=output_imgs[1]

    return fix_resized,mov_resized

def flip_image_transform(xy_dims,mpp):
    flip_txt=Path( os.path.dirname(__file__) ) / "maps" /"transforms"/"flip.txt"
    width_pix,height_pix=xy_dims
    xy_centroid=[(width_pix//2)*mpp,(height_pix//2)*mpp]
    flip_trf=itk.ParameterObject.New()
    flip_trf.AddParameterFile(str(flip_txt))
    flip_trf.SetParameter(0,"Size", [str(width_pix),str(height_pix) ])
    flip_trf.SetParameter(0,"Spacing",[str(mpp),str(mpp)])
    flip_trf.SetParameter(0,"CenterOfRotationPoint",[str(val) for val in xy_centroid ])
    return flip_trf



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
    qc_dir=out_root_dir / "qc_reg"
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







def main(version):

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

    validate_align_args(args)
    #Define and create qc directories
    outdirs=make_outdirs(output_dir)

    #Extract image properties,i.e. pyramidal, mpp,dimensions, etc.
    Fix=ImageFileGateway(fixed_img_path,mpp_fix)
    Mov=ImageFileGateway(moving_img_path,mpp_mov,fliph=flip_horizontally)

    fixed_props=Fix.props
    moving_props=Mov.props

    if moving_props["pyramid"]:
        out_levels=moving_props["levels"]
    else:
        out_levels=levels

    #Extract channels of fixed image and moving image channels to be used for registration.
    #Resize both fixed and moving image to have the same mpp
    reg_fixed_img,reg_moving_img=resize_and_extract_channels(Fix,Mov,fixed_ch,moving_ch,reg_mpp)
    #Save reference images in qc_dir for reference
    tifff.imwrite(outdirs["refchns"]/f"fixed_ch-{fixed_ch}.tif", reg_fixed_img,photometric="minisblack")
    tifff.imwrite(outdirs["refchns"]/f"moving_ch-{moving_ch}.tif",reg_moving_img,photometric="minisblack")

    #Calculate initial alignment
    if apply_initial_alignment:
        init_trf_dir=outdirs["transforms"] / "00_initial"
        init_trf_dir.mkdir(parents=True,exist_ok=True)
        inter_fixed_img,inter_moving_img=resize_and_extract_channels(Fix,Mov,fixed_ch,moving_ch,key_mpp)

        tifff.imwrite(outdirs["keypoints"]/"fixed_keypoints.tif",inter_fixed_img,photometric="minisblack")
        tifff.imwrite(outdirs["keypoints"]/"moving_keypoints.tif",inter_moving_img,photometric="minisblack")
        height,width=reg_fixed_img.shape

        init_trf=initial_align.get_initial_trf(inter_fixed_img,
                                               inter_moving_img,
                                               key_mpp,
                                               outdirs["keypoints"],#directory to save ransac_matches.png
                                               output_dict={"mpp":reg_mpp,"xy_dims":[width,height]}
                                               )

        conformed_trf=initial_align.conform_trf_object(init_trf)
        mov_itk=itk.GetImageFromArray(img_as_float32(reg_moving_img))
        mov_itk.SetSpacing([reg_mpp,reg_mpp])
        reg_moving_img=itk.transformix_filter(mov_itk,conformed_trf,log_to_console=False)
        #Save results for qc
        save_init_trf_maps(init_trf,init_trf_dir)
        tifff.imwrite(init_trf_dir/"moving_init_aligned.tif",reg_moving_img,photometric="minisblack")
    else:
        init_trf=None
    #Extract transforms from registering with registration scheme (rigid,affine,bsplines).
    transformations_map=register_references(
                        reg_fixed_img,
                        reg_moving_img,
                        reg_mpp,
                        outdirs["transforms"],
                        reg_scheme,
                        apply_initial_alignment,
                        grid_spacing
                        )
    # Adjust initial transform according to final dimensions and pixel size
    output_img_size=(fixed_props["size_x"],fixed_props["size_y"])
    out_mpp=mpp_fix
    transformations_map=create_final_trf_map(transformations_map,
                                             output_img_size,
                                             out_mpp,
                                             init_trf
                                             )
    # Write all final transformations into the fullres_trf folder
    no_of_trf_maps=transformations_map.GetNumberOfParameterMaps()
    transformations_map.WriteParameterFile(transformations_map.GetParameterMaps(),
                                           [str(outdirs["fullres_trf"]/f"trf_{i:02d}.txt") for i \
                                            in range(no_of_trf_maps)]
                                           )


    #Apply transformations to the moving image and upscale to the dimensions of the fixed image
    registered_img_generator=apply_transform(
                                    Mov,#moving_img_path,
                                    transformations_map,
                                    out_mpp
                                    )
    #resize_mpp,
    #(fixed_props["size_y"],fixed_props["size_x"])
    #)

    if not test_mode:
        out_file_name=f'{ (moving_img_path.stem).split(".ome")[0] }_{suffix}.ome.tif'

        out_img_path=create_pyramid(
                    [registered_img_generator],
                    out_levels,
                    output_dir,
                    out_file_name,
                    moving_props["data_type"],
                    moving_props["color_type"],
                    compression_method
                    )
        #Update moving image props after registration
        moving_props_out=ImageFileGateway(out_img_path,out_mpp).props
        if markers:
            channel_names=pd.read_csv(markers)["marker_name"].tolist()
        else:
            channel_names=[f"Channel-{ch}" for ch in range(moving_props_out["channels"])]
        #Write metadata in OME format into the pyramidal file
        ome_xml=ome_writer.create_ome(channel_names,moving_props_out,version)
        tifff.tiffcomment(out_img_path, ome_xml.encode("utf-8"))


if __name__ == '__main__':
    _version = 'v1.5.0'

    tracemalloc.start()
    st = time.time()

    main(_version)

    print("Memory peak:",((10**(-9))*tracemalloc.get_traced_memory()[1],"GB"))
    rt = time.time() - st
    tracemalloc.stop()
    print(f"Script finished in {rt // 60:.0f}m {rt % 60:.0f}s")