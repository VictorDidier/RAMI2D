import tifffile as tifff
import openslide
from pathlib import Path
import numpy as np
from skimage import transform
from skimage.color import rgb2hed
from skimage.exposure import rescale_intensity
from skimage.util import img_as_float32
from skimage.filters import threshold_otsu
from scipy.ndimage import binary_dilation
import itk



class ImageFileGateway:

    def __init__(self,image_file,mpp,fliph=False):
        """
        data can be a file to your image file, a numpy array or
        a slide object.
        """
        self.file =image_file
        self.is_slide=self._is_slide(image_file)
        self.is_tiff=self._is_tiff(image_file)
        self.props=self.get_image_properties(mpp)
        self.flip_h=fliph


    def _is_slide(self,path):
        try:
            is_slide_path=isinstance(openslide.OpenSlide( path), openslide.OpenSlide)
            exclude_ome=[".ome.tiff",".ome.tif"]
            if any(str(path).endswith(ext) for ext in exclude_ome):
                is_slide_path=False
        except:
            is_slide_path=False
        return is_slide_path

    def _is_tiff(self,path):
        file_extensions=[".tif",".tiff",".ome.tiff",".ome.tif"]
        is_tiff_path=any(str(path).endswith(ext) for ext in file_extensions)
        return is_tiff_path


    def get_image_properties(self,mpp):
        # Determine type and call appropriate method
        if self.is_slide:
            return self.slide_props(mpp)
        elif self.is_tiff:
            return self.array_props(mpp)
        else:
            raise ValueError("Unknown data type")

    def get_pyramidal_level(self,level=0,ch=0):
        if self.is_slide:
            return self.slide_level(level)
        elif self.is_tiff:
            return self.tiff_level(level,ch)
        else:
            raise ValueError("Unknown data type")

    def get_first_nth_pyramidal_levels(self,n,ch=0):
        if self.is_slide:
            for lev in range(n):
                yield self.slide_level(lev)
        elif self.is_tiff:
            for lev in range(n):
                yield self.tiff_level(lev,ch)
        else:
            raise ValueError("Unknown data type")

    def slide_props(self, mpp,background="white"):
        """Get detailed image properties including color information"""
        # Read a small region to analyze color properties
        level=0
        slide = openslide.OpenSlide( self.file)
        test_region = slide.read_region((0, 0), level, (100, 100))
        test_array = np.array(test_region)
        width,height=slide.level_dimensions[0]
        # Validate if scaling factors of the pyramid levels are the same
        scaling_factors=slide.level_downsamples
        down_factors=[scaling_factors[i]//scaling_factors[i-1]
                    for i in range(1,len(scaling_factors))
                ]

        unique_vals, counts = np.unique(down_factors, return_counts=True)
        mode = unique_vals[np.argmax(counts)]

        compliant_scales_idx=[True]#add the first layer, i.e. highest resolution should always be included
        compliant_scales_idx.extend([val==mode for val in down_factors])
        dims_schedule=np.array(list(slide.level_dimensions))
        dims_schedule=dims_schedule[compliant_scales_idx].tolist()
        dims_schedule=[(y,x) for x,y in dims_schedule]

        data_type=test_array.dtype.name

        props = {
            "pixel_size":mpp,
            "pixel_size_unit":"µm",
            "data_type": data_type,
            "pyramid":len(dims_schedule)>1,
            "levels":len(dims_schedule),
            "size_x":width,
            "size_y":height ,
            "bits": data_type.split("uint")[-1],
            #'mode': test_region.mode,
            'background':background,
            'pyramid_schedule':dims_schedule,
            'channels': test_array.shape[2] if len(test_array.shape) == 3 else 1,
            "ch_idx":2
            }

        # Determine color type
        if props['channels'] == 4:
            props['color_type'] = 'RGBA'
        elif props['channels'] == 3:
            props['color_type'] = 'RGB'
        else:
            props['color_type'] = 'grayscale'

        return props

    def array_props(self,mpp):
        img_path=self.file
        with tifff.TiffFile(img_path) as tif:
            #BASIC INFO
            pyr_levels=len(tif.series[0].levels)
            is_pyramid=pyr_levels > 1
            data_type=tif.series[0].dtype.name
            no_of_channels=len(tif.pages)
            multichannel=no_of_channels>1
            #COLOR INFO
            photometric = tif.pages[0].photometric
            if (photometric==0 or photometric==1):
                color_type="grayscale"
            elif photometric==2:
                color_type="RGB"
            elif photometric>2:
                raise ValueError(f"Photometric interpretation of {self.file} is currently not supported.  The image in the file should be grayscale or RGB")
            #DIMENSIONS INFO
            axes=tif.pages[0].axes
            ch_idx=None if axes.find("S")==-1 else axes.find("S")
            if multichannel:
                putative_ch_index=np.select([color_type=="grayscale",color_type=="RGB"],[0,2]).item()
                putative_offset=np.select([color_type=="grayscale",color_type=="RGB"],[1,0]).item()
                if ch_idx==None:
                    ch_idx=putative_ch_index
                    offset=putative_offset
                else:
                    offset=0
                x_idx=axes.find("X")+offset
                y_idx=axes.find("Y")+offset
            else:
                x_idx=axes.find("X")
                y_idx=axes.find("Y")
            dims_schedule=[(lev.shape[y_idx],lev.shape[x_idx]) for lev in tif.series[0].levels]#(Y,X) dimensions
            height,width=dims_schedule[0]
        #COLLECT INFO IN A DICTIONARY
        img_props={
                "pixel_size":mpp,
                "pixel_size_unit":"µm",
                "data_type":data_type,
                "pyramid":is_pyramid,
                "levels":pyr_levels,
                "size_x":width,
                "size_y":height ,
                "bits": data_type.split("uint")[-1],
                "pyramid_schedule":dims_schedule,
                "channels":no_of_channels,
                "color_type":color_type,
                "ch_idx":ch_idx
               }
        return img_props

    def tiff_level(self,level,ch=0):
        path=self.file
        with tifff.TiffFile(path) as tif:
            return tif.series[0].levels[level].pages[ch].asarray()

    @staticmethod
    def _convert_rgba_to_rgb(rgba_array, background='white'):
        """
        Convert RGBA image to RGB with specified background
        Parameters:
        - rgba_array: numpy array of shape (H, W, 4)
        - background: 'white' or 'black' background color
        """
        if rgba_array.shape[2] != 4:
            return rgba_array

        r, g, b, a = rgba_array[:,:,0], rgba_array[:,:,1], rgba_array[:,:,2], rgba_array[:,:,3]

        # Normalize alpha to [0, 1]
        a = a.astype(np.float32) / 255.0

        if background == 'white':
            # Composite over white background
            r = (r * a + 255 * (1 - a)).astype(np.uint8)
            g = (g * a + 255 * (1 - a)).astype(np.uint8)
            b = (b * a + 255 * (1 - a)).astype(np.uint8)
        else:  # black background
            r = (r * a).astype(np.uint8)
            g = (g * a).astype(np.uint8)
            b = (b * a).astype(np.uint8)

        return np.stack([r, g, b], axis=2)

    def slide_level(self,level):
        slide=openslide.OpenSlide( self.file)
        height,width=self.props["pyramid_schedule"][level]
        level_img = slide.read_region((0, 0), level, (width,height))
        level_array = np.array(level_img)
        if self.props["color_type"]=="RGBA":
            print(f"Level {level}: Converting RGBA to RGB with {self.props['background']} background")
            level_array = ImageFileGateway._convert_rgba_to_rgb(level_array, self.props["background"])
        elif self.props["color_type"]=="RGB":  # RGB
            print(f"Level {level}: RGB format detected")
        elif level_array.shape[2] == 2:
            print(f"Level {level}: Unexpected format with {level_array.shape[2]} channels")
        return level_array

    def resize(self,mpp_out,ch=0):
        """
        This function extracts a channel from a pyramidal tifff_stack and resizes the image
        as to match the target microns_per_pixel

        Args:
            list_of_dicts (list): list of dictionaries with common keys
        Returns:
            merged_dict (dict): dictionary with the values stored in lists
        """
        path=self.file
        mpp_in=self.props["pixel_size"]
        pyramid_dims=self.props["pyramid_schedule"]
        img_type=self.props["data_type"]

        resize_factor=mpp_in/mpp_out
        target_dim=np.rint( resize_factor*np.array(pyramid_dims[0]) )
        target_dim=[int(element) for element in target_dim]
        nearest_lvl_index=np.argmin( np.abs( [target_dim[0]-element[0] for element in pyramid_dims] ) )

        if self.is_tiff:
            #img_arr=tifff.imread(path,series=0,key=ch,level=nearest_lvl_index)
            img_arr=self.tiff_level(nearest_lvl_index,ch)
        if self.is_slide:
            img_arr=self.slide_level(nearest_lvl_index)

        if len(img_arr)==2:#grayscale
            pass
        elif len(img_arr)==3:#rgb
            target_dim.insert(self.props["ch_idx"],3)

        output_img=transform.resize(img_arr, output_shape=target_dim,order=0,preserve_range=True).astype(img_type)

        if self.flip_h:
            output_img=np.flip(output_img,axis=1)
        return output_img

def get_hed_channels(rgb_img,color_axis):

    ihc_hed = rgb2hed(rgb_img,channel_axis=color_axis)
    hemato=np.take(ihc_hed,0,axis=color_axis)
    eosin=np.take(ihc_hed,1,axis=color_axis)
    dab=np.take(ihc_hed,2,axis=color_axis)
    gray_scale=np.zeros(hemato.shape+(3,),dtype="uint8")
    for ch,image in enumerate([hemato,eosin,dab]):
        gray_scale[:,:,ch]=np.rint( rescale_intensity(image,out_range=(0,255) ) ).astype("uint8")
    return gray_scale

def fast_percentile(arr, low=1, high=99):
    """Create mask using np.partition for O(n) performance"""
    n = arr.size

    # Calculate indices for percentiles
    k_low = max(0, int(np.ceil(n * low / 100)) - 1)
    k_high = min(n-1, int(np.ceil(n * high / 100)) - 1)

    # Use partition to get the k-th smallest values
    partitioned = np.partition(arr.flatten(), [k_low, k_high])
        # Get the actual percentile values
    p_low = partitioned[k_low]
    p_high = partitioned[k_high]

    return p_low,p_high

def measure_contrast(image):
    p1, p99 = fast_percentile(image,1,99)
    mask = (image >= p1) & (image <= p99)
    threshold = threshold_otsu( image[ mask ] )
    background_pixels=image[image <= threshold]
    foreground_pixels=image[image > threshold]
    bg_mean=np.mean(background_pixels)
    fg_mean=np.mean(foreground_pixels)
    try:
        range=np.iinfo(image.dtype).max-np.iinfo(image.dtype).min
    except ValueError:
        range=np.finfo(image.dtype).max-np.finfo(image.dtype).min
    """
    normalized root mean squared: are the pixels in the image populated with values higher than 0? Are there sufficient pixels populated with the latter condition?
    An ideal value of norm_rsm is 0.5 for an image with a bimodal intensity distribution of pixels,
    e.g. half pixels are at the lowest value of the available range and the other half has the maximum value of the range.
    """
    norm_rsm=np.std(image)/range
    """
    michelson: how high is the contrast between background signal and foreground signal.  Ideal value is 1, i.e. background is effectively null.
    """
    michelson=(fg_mean-bg_mean)/(fg_mean+bg_mean)

    return norm_rsm,michelson
    #foreground_ceiling=np.percentile( foreground_pixels,99 )
    #gray_scale[:,:,ch]=np.rint( rescale_intensity(image,in_range=(background_baseline,foreground_ceiling),out_range=(0,255) ) ).astype("uint8")

def enhance_contrast(image):

    try:
        range_max=np.iinfo(image.dtype).max
        range_min=np.iinfo(image.dtype).min
        is_img_int=True
    except ValueError:
        range_max=np.finfo(image.dtype).max
        range_min=np.finfo(image.dtype).min
        is_img_int=False
    data_type=image.dtype.name
    intensity_output_range=(range_min,range_max)
    img_float=img_as_float32(image)
    p1, p99 = fast_percentile(img_float,1,99)
    mask = (img_float >= p1) & (img_float <= p99)
    threshold = threshold_otsu( img_float[ mask ] )
    background_pixels=img_float[ img_float <= threshold ]
    foreground_pixels=img_float[ img_float > threshold ]
    background_baseline=np.mean(background_pixels)
    foreground_ceiling=np.percentile( foreground_pixels,99 )
    image_enhanced=rescale_intensity(img_float, in_range=(background_baseline,foreground_ceiling), out_range=intensity_output_range )

    if is_img_int:
        image_enhanced=np.rint(image_enhanced).astype(data_type)
    else:
        image_enhanced=image_enhanced.astype(data_type)

    return image_enhanced

def get_foreground_mask(arr,mpp):
    thresh=threshold_otsu(arr)
    foreground_mask = np.zeros(arr.shape,dtype="uint8")
    foreground_mask[ arr > thresh]=1
    dilated_mask= binary_dilation(foreground_mask, iterations=50)
    foreground_mask[dilated_mask]=1
    mask=itk.GetImageFromArray(foreground_mask)
    mask.SetSpacing([mpp,mpp])
    return mask