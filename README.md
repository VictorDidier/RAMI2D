![Logo](https://github.com/VictorDidier/RAMI2D/blob/main/data/figs/logo2.png)
# DESCRIPTION

(RAMI2D) Robust Alignment of Multichannel Images in 2D is a command-line interface tool that allows the registration of multi-channel images in a convenient way by exposing the main parameters that control the registration outcome.  The flowchart below shows how the tool processes the images, this workflow is the usual footprint of a registration process and can be found in tools like [RegisterVirtualSlices](https://github.com/fiji/register_virtual_stack_slices) or [palom](https://github.com/labsyspharm/palom).

The convenience that RAMI2D provides is an easy interface to use the power and features of [itk-elastix](https://github.com/InsightSoftwareConsortium/ITKElastix), i.e. registration models, sampling strategies and rendering registration results not only as an image but as a set of transformation parameters that can be saved in a file. RAMI2D packs some of the models found in [itk-elastix](https://github.com/InsightSoftwareConsortium/ITKElastix)  to offer 3 pre-defined registration schemes: 1) Rigid, 2) Rigid+Affine 3) Rigid+Affine+Bsplines, each of them providing more geometrical adaptability and thus more control in the final outcome.

RAMI2D provides an option to find keypoints via SIFT and RANSAC for images that are initially very missaligned, e.g. rotated in large angles, images with different dimensions or different fields of view. These keypoints are later used to construct an itk transformation map that is ingested as an initial alignment to the pre-defined registration schemes.

RAMI2D offers the following features:

### Features
- Supported formats: Multichannel greyscale and single-page RGB ome.tif,tif. Any format supported by [OpenSlide](https://openslide.org/).
- Multimodal registration: different microscopy modalities can be registered, whatever produces a grayscale or RGB image in the formats above.
- Registration of consecutive slices: Can be used to register consecutive slices.
- Multi-scale: Fixed and moving images can have different pixel-sizes.
- Multi-step registration scheme: Scheme-1) Rigid, Scheme-2) Rigid->Affine, Scheme Scheme-3)Rigid->Affine->Bsplines.
- Test mode: check intermediate results in low-resolution before applying a result to a full-resolution image and all its channels.

# FLOWCHART

![Logo](https://github.com/VictorDidier/RAMI2D/blob/main/data/figs/flowchart-horizontal-annotations.png)

# TERMS
- Fixed image: image to register against.
- Moving image: image that will be transformed to match the structures and dimensions of the fixed image.
- mpp: microns per pixel, i.e. pixel size in micrometers.

# CLI arguments
The main script is in ./src/rami2d/register.py.
You can visualize a more detailed documentation for each argument in your terminal via the following command
```
python register.py --help
```

### Fixed image arguments
| Argument|Type|Description|Default value|Required|
|---------|----|-----------|-------------|-------------|
| -fix    | Path | path to fix image  | NA |True|
| -mpp-fix| float | pixel-size in micrometers| NA |True|
|-ifix    | integer or string h,e,d | if integer then 0-based index of channel to be used for registration. If string Hematoxyling, Eosin or DAB|NA|True|

### Moving image arguments
| Argument|Type|Description|Default value|Required|
|---------|----|-----------|-------------|-------------|
| -mov    | Path | path to fix image  | NA |True|
| -mpp-mov| float | pixel-size in micrometers| NA |True|
|-imov    | integer or string h,e,d | if integer then 0-based index of channel to be used for registration. If string Hematoxyling, Eosin or DAB|NA|True|

### Registration arguments
| Argument|Type|Description|Default value|Required|
|---------|----|-----------|-------------|-------------|
| -a     | Boolean flag | Implement initial alignent via finding keypoints | NA |False|
| -mpp-key | float | image resolution in micrometers to be used for searching keypoints | NA |False|
| -mpp-reg | float | image resolution in micrometersto be used for implemnting the registration scheme | NA |True|
| -rsc | integer | Select one of the following registration schemes 1,2,3,check the list in features section | 1 |False|
| -gs | two integers | x y size of grid to be used in bsplines in micrometers (only useful for -rsc 3) | 1000 1000 |False|

### Output arguments
| Argument|Type|Description|Default value|Required|
|---------|----|-----------|-------------|-------------|
| -o     | Path| path to directory where registered image will be saved | NA |True|
| -fn | string | suffix to append to the registered image| "registered" |False|
| -pl | integer | total number of pyramidal levels in the output image.If the moving image is already pyramidal the output will have same number of levels and this argument will be ignored| 8 |False|
| -comp | string | compression algorithm, by default greyscale are compressed with lzw and rgb with jpeg2000 | "default" |False|
| -m | Path | Path to a csv file with a column named marker_name, each row is the name of the channel in the ome metadata of the output file | NA |False|
| -test | Boolean flag | Activate test mode to skip writting the final full resolution image, you can still check the registration results on the -mpp-reg resolution in the qc folder | NA |False|

# INSTALLATION AND USAGE
### via creating a conda environment
- (1) Download the scripts in the [./src/rami2d/](https://github.com/VictorDidier/RAMI2D/tree/main/src/rami2d) folder.
- (2) Download the [conda_env.yml](https://github.com/VictorDidier/RAMI2D/blob/main/conda_env.yml) file.
- (3) Create conda environment:
```
conda env create -f *local_directory*/conda_env.yml -n *custom_environment_name*
```
- (4) Activate environment:
```
conda activate *custom_environment_name*
```
- (5) Check the CLI of the register.py script by executing:
```
python *local_directory*/register.py --help
```
- (6) Execute register.py with your correspondent entries for the CLI, for example:
```
python *local_directory*/register.py -o *local_outdir* -fix "H&E_image.ndpi" -mpp-fix 0.3 -ifix "h" \
-mov "N-Fluorescence-channels.tif" -mpp-mov 0.2 -imov 0 \
-mpp-key 8 -mpp-reg 1 -a -rsc 2
```
In the call above the image N-Fluorescence-channels.tif will be registered to the H&E_image.ndpi, the reference channels for registration are 0  and Hematoxylin("h") respectively.  The mpp of each image is 0.3 and 0.2. Since the argument -a has been called an inital alignment will be implemented with the reference channels resized at a 8mpp, then the registration scheme number 2, i.e. Rigid+Affine, will be applied at image resolutions of 1 mpp.

### via container

**Singularity**
- (1) Download container:

```
singularity pull docker://
```
This will download a container named

- (2) Execute the register.py script inside the /tools folder in the .sif container.  Be aware of two things in the example below,(a) the variables mnt, media and tools are names of folders inside the container and need no editing in the example below. (b) We suppose that the macsima and maldi stacks and associated .csv information is in a local directory *input_directory*, while the output of the script will be written in a different local directory *output_directory*.

# ACKNOWLEDGEMENTS
Data sources:
1) Data available on Synapse: https://www.synapse.org/Synapse:syn51449054
from Wünnemann, F., Sicklinger, F., Bestak, K. et al.
Spatial multiomics of acute myocardial infarction reveals immune cell infiltration through the endocardium.
Nat Cardiovasc Res 4, 1345-1362 (2025). https://doi.org/10.1038/s44161-025-00717-y
2) Modified from https://github.com/nf-core/test-datasets/tree/modules/data/imaging/hne_multiplexed


