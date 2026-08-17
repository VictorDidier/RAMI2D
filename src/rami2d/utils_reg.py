import os
import warnings
from pathlib import Path
import itk
from skimage.util import img_as_float32
import numpy as np
import dask.array as da
from dask import delayed
#local scripts
from . import processing_tools as prt
from .processing_tools import ImageFileGateway





def register_references(fixed,moving,mpp,out_trf_dir,scheme,init_align,grid_spacing,maskreg):
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
    if maskreg:
        fixed_mask=prt.get_foreground_mask(fixed,mpp)
    else:
        fixed_mask=None

    #mov_updated below is already an itk image with the mpp spacing
    loop_idx=0
    for Reg,Out in zip(registration_maps,qc_trf_out):
        reg_map=itk.ParameterObject.New()
        reg_map.AddParameterFile(str(Reg))

        if maskreg:
            reg_map.SetParameter(0,
                                 "ImageSampler",
                                 ["RandomSparseMask"]
                                )

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
                                                                    fixed_mask=fixed_mask,
                                                                    output_directory=str(Out),
                                                                    log_file_name="log.txt",
                                                                    log_to_console=False
                                                                    )

        global_trf_map.AddParameterMap(result_trf_params.GetParameterMap(0))
        loop_idx+=1

    return global_trf_map

def apply_transform_iter(img_object,transform_map,in_mpp=None,is_label=False):

    out_mpp=float(transform_map.GetParameter(0,"Spacing")[0])

    if isinstance(img_object,Path) or isinstance(img_object,str):
        if in_mpp:
            img_object=ImageFileGateway(img_object,in_mpp)
        else:
            raise ValueError(f"""An image path input requires 
                             the microns_per_pixel argument(in_mpp)""")
            
    else:
        pass

    if is_label:
        for n in range(transform_map.GetNumberOfParameterMaps()):
            transform_map.SetParameter(n,"FinalBSplineInterpolationOrder", "0")

    

    color_interpretation=img_object.props["color_type"]
    if color_interpretation=="grayscale":
        no_of_ch=img_object.props["channels"]
    elif color_interpretation in ["RGB","RGBA"]:
        no_of_ch=1#only single page RGB images are accepted

    for ch_index in range(no_of_ch):
        if color_interpretation=="grayscale":
            result=itk.GetImageFromArray( img_object.resize(out_mpp,ch=ch_index))
            result.SetSpacing([out_mpp,out_mpp])
            result=itk.transformix_filter(result,transform_map,log_to_console=False)
            yield itk.GetArrayFromImage( result )
        elif color_interpretation in ["RGB","RGBA"] :
            #result=itk.GetImageFromArray( img_object.resize(mpp_full)[:,:,ch_index])
            rgb_input=img_object.resize(out_mpp)
            rgb_output=[]
            for color_index in range(3):
                #result=itk.GetImageFromArray(rgb_input[:,:,color_index])
                result=itk.GetImageFromArray(np.take(rgb_input,color_index,axis=img_object.props["ch_idx"]))
                result.SetSpacing([out_mpp,out_mpp])
                result=itk.transformix_filter(result,transform_map,log_to_console=False)
                rgb_output.append(itk.GetArrayFromImage( result ))
            yield np.stack(rgb_output, axis=2)

def apply_transform(img_object,transform_map,ch_index=0,in_mpp=None,is_label=False):

    out_mpp=float(transform_map.GetParameter(0,"Spacing")[0])

    if isinstance(img_object,Path) or isinstance(img_object,str):
        if in_mpp:
            img_object=ImageFileGateway(img_object,in_mpp)
        else:
            raise ValueError(f"""An image path input requires 
                             the microns_per_pixel argument(in_mpp)""")
    else:
        pass

    if is_label:
        for n in range(transform_map.GetNumberOfParameterMaps()):
            transform_map.SetParameter(n,"FinalBSplineInterpolationOrder", "0")

    color_interpretation=img_object.props["color_type"]

    if color_interpretation=="grayscale":
        result=itk.GetImageFromArray( img_object.resize(out_mpp,ch=ch_index))
        result.SetSpacing([out_mpp,out_mpp])
        result=itk.transformix_filter(result,transform_map,log_to_console=False)
        return itk.GetArrayFromImage( result )
    elif color_interpretation in ["RGB","RGBA"] :
        #result=itk.GetImageFromArray( img_object.resize(mpp_full)[:,:,ch_index])
        rgb_input=img_object.resize(out_mpp)
        rgb_output=[]
        for color_index in range(3):
            result=itk.GetImageFromArray(np.take(rgb_input,color_index,axis=img_object.props["ch_idx"]))
            result.SetSpacing([out_mpp,out_mpp])
            result=itk.transformix_filter(result,transform_map,log_to_console=False)
            rgb_output.append(itk.GetArrayFromImage( result ))
        return np.stack(rgb_output, axis=2)


@delayed
def transform_single_page(img_object,transform_map,color_interpretation,ch_index,out_mpp):
    
            
    if color_interpretation=="grayscale":
        result=itk.GetImageFromArray( img_object.resize(out_mpp,ch=ch_index))
        result.SetSpacing([out_mpp,out_mpp])
        result=itk.transformix_filter(result,transform_map,log_to_console=False)
        return itk.GetArrayFromImage( result )
    elif color_interpretation in ["RGB","RGBA"] :
        #result=itk.GetImageFromArray( img_object.resize(mpp_full)[:,:,ch_index])
        rgb_input=img_object.resize(out_mpp)
        rgb_output=[]
        for color_index in range(3):
            result=itk.GetImageFromArray(np.take(rgb_input,color_index,axis=img_object.props["ch_idx"]))
            result.SetSpacing([out_mpp,out_mpp])
            result=itk.transformix_filter(result,transform_map,log_to_console=False)
            rgb_output.append(itk.GetArrayFromImage( result ))
        return np.stack(rgb_output, axis=2)
    
def apply_transform_delayed(img_object,transform_map,in_mpp=None,is_label=False):
    
    if isinstance(img_object,Path) or isinstance(img_object,str):
        if in_mpp:
            img_object=ImageFileGateway(img_object,in_mpp)
        else:
            raise ValueError(f"""An image path input requires 
                             the microns_per_pixel argument(in_mpp)""")
    else:
        pass
    
    out_mpp=float(transform_map.GetParameter(0,"Spacing")[0])
    color_interpretation=img_object.props["color_type"]
    if is_label:
        for n in range(transform_map.GetNumberOfParameterMaps()):
            transform_map.SetParameter(n,"FinalBSplineInterpolationOrder", "0")

    if color_interpretation=="grayscale":
        no_of_ch=img_object.props["channels"]
    elif color_interpretation in ["RGB","RGBA"]:
        no_of_ch=1#only single page RGB images are accepted

    transformed_stack=[transform_single_page(img_object,transform_map,color_interpretation,ch,out_mpp) 
                       for ch in range(no_of_ch)
                        ]
    
    return transformed_stack
    


def create_final_trf_map(trf,output_size,out_mpp,init_map=None,init_map_conformed=False):
    #Edit initial transformation map
    final_transform_map=itk.ParameterObject.New()
    trf_maps=[]
    if init_map:
        for n in range(init_map.GetNumberOfParameterMaps()):
            init_map.SetParameter(n,"Size", [str(val) for val in output_size ])
            init_map.SetParameter(n,"Spacing",[str(out_mpp),str(out_mpp)])
            trf_maps.append(init_map.GetParameterMap(n))
        if init_map_conformed:
            trf_maps.reverse()

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

def generate_flip_transform(out_dimsxy,out_mpp):
    transforms_dir=Path( os.path.dirname(__file__) ) / "maps" /"transforms"
    flip_template=transforms_dir / "flip.txt"
    width_pix,height_pix=out_dimsxy
    image_center=[(width_pix/2)*out_mpp,(height_pix/2)*out_mpp]
    flip_trf=itk.ParameterObject.New()
    flip_trf.AddParameterFile(str(flip_template))
    flip_trf.SetParameter(0,"Size", [str(width_pix),str(height_pix) ])
    flip_trf.SetParameter(0,"Spacing",[str(out_mpp),str(out_mpp)])
    flip_trf.SetParameter(0,"CenterOfRotationPoint",[str(val) for val in image_center ])
    return flip_trf



