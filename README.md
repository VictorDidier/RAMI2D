![Logo](https://github.com/VictorDidier/RAMI2D/blob/main/data/logo/logo2.png)
# DESCRIPTION

(RAMI2D) Robust Alignment of Multichannel Images in 2D is a command-line interface tool that allows the registration of multi-channel images in a convenient way by exposing the main parameters that control the registration outcome.  The flowchart below shows how the tool processes the images, this workflow is the usual footprint of a registration process and can be found in tools like [RegisterVirtualSlices](https://github.com/fiji/register_virtual_stack_slices) or [palom](https://github.com/labsyspharm/palom).

The convenience that RAMI2D provides is an easy interface to use the power and features of [itk-elastix](https://github.com/InsightSoftwareConsortium/ITKElastix), i.e. registration models, sampling strategies and rendering registration results not only as an image but as a set of transformation parameters that can be saved in a file. RAMI2D packs some of the models found in [itk-elastix](https://github.com/InsightSoftwareConsortium/ITKElastix)  to offer 3 pre-defined registration schemes: 1) Rigid, 2) Rigid+Affine 3) Rigid+Affine+Bsplines, each of them providing more geometrical adaptability and thus more control in the final outcome.

RAMI2D provides an option to find keypoints via SIFT and RANSAC for images that are initially very missaligned, e.g. rotated in large angles, images with different dimensions or different fields of view. These keypoints are later used to construct an itk transformation map that is ingested as an initial alignment to the pre-defined registration schemes.

RAMI2D offers the following features:

## Features
- Supported formats: ome.tif,tif, any .ndpi
- Multimodal registration: different microscopy modalities can be registered, whatever produces a grayscale or RGB image in the formats above
- Registration of consecutive slices: Can be used to register consecutive slices.
- Multi-scale: Fixed and moving images can have different pixel-sizes.
- Multi-step registration scheme: Scheme-1) Rigid, Scheme-2) Rigid->Affine, Scheme Scheme-3)Rigid->Affine->Bsplines.
- Test mode: check intermediate results in low-resolution before applying a result to a full-resolution image and all its channels.

# WORKFLOW CHART



## CLI arguments
The main script is in ./src/rami2d/register.py.
You can visualize in your terminal the CLI documentation using the following command
```
python register.py --help
```

### Fixed image arguments
| Argument|Type|Description|Default value|
|---------|----|-----------|-------------|
| -fix     | Path | output directory where the registered maldi & mics image will be saved | NA |
| -mpp-fix | float | pixel-size in micrometers | NA |
|-ifix | integer | 0-based index of channel to be used for registration|NA|

### Moving image arguments
| Argument|Type|Description|Default value|
|---------|----|-----------|-------------|
| -mov     | Path | output directory where the registered maldi & mics image will be saved | NA |
| -mpp-mov | float | pixel-size in micrometers | NA |
|-imov | integer | 0-based index of channel to be used for registration|NA|

### Registration arguments
| Argument|Type|Description|Default value|
|---------|----|-----------|-------------|
| -a     | Boolean flag | Implement initial alignent via finding keypoints | NA |
| -mpp-key | float | resolution in micrometers to be used for searching keypoints | NA |
| -mpp-reg | float | resolution in micrometers to be used for implemnting the registration scheme | NA |
| -rsc | integer | Select one of the following registration schemes 1,2,3,check the list in features section | 1 |
| -gs | two integers | x y size of grid to be used in bsplines in micrometers (only useful for -rsc 3) | 1000 1000 |

### Output arguments
| Argument|Type|Description|Default value|
|---------|----|-----------|-------------|
| -o     | Path| path to directory where registered image will be saved | NA |
| -fn | string | suffix to append to the registered image| "registered" |
| -pl | integer | total number of pyramidal levels in the output image.If the moving image is already pyramidal the output will have same number of levels and this argument will be ignored| 8 |
| -comp | string | compression algorithm, by default greyscale are compressed with lzw and rgb with jpeg2000 | "default" |
| -m | Path | Path to a csv file with a column named marker_name, each row is the name of the channel in the ome metadata of the output file | NA |
| -test | Boolean flag | Activate test mode to skip writting the final full resolution image, you can still check the registration results on the -mpp-reg resolution in the qc folder | NA |

## via python
- (1) Download the [./scripts](https://github.com/SchapiroLabor/femur-multi-omics/tree/main/scripts) folder
- (2) Download the [environment.yml](https://github.com/SchapiroLabor/femur-multi-omics/blob/main/environment.yml) file
- (3) Create conda environment:
```
conda env create -f *local_directory*/environment.yml -n *custom_environment_name*
```
- (4) Activate environment:
```
conda activate *custom_environment_name*
```
- (5) Check the CLI of the register.py script by executing:
```
python *local_directory*/register.py --help
```
or check the CLI documentation below.

- (6) Execute register.py with your correspondent entries for the CLI, for example:
```
python *local_directory*/register.py -o *output_directory*  -inmi *macsima_stack.tif* \
-mppmi *0.170* -idxmi *0* *4* -markmi *markers.csv* -inma *maldi_stack.tif* \
-mppma *5* -idxma *10* -markma *maldi_markers.csv*
```
In the example above we suppose the dense marker in the MACSima images is in the channel with index 0 and the fiducial marker is in channel 4.  The latter marker is associated to channel 10 of the maldi stack.

## via container

**Singularity**
- (1) Download container:

```
singularity pull docker://ghcr.io/schapirolabor/femur-multi-omics:v1.5.0
```
This will download a container named femur-multi-omics:v1.5.0.sif

- (2) Execute the register.py script inside the /tools folder in the .sif container.  Be aware of two things in the example below,(a) the variables mnt, media and tools are names of folders inside the container and need no editing in the example below. (b) We suppose that the macsima and maldi stacks and associated .csv information is in a local directory *input_directory*, while the output of the script will be written in a different local directory *output_directory*.

Example:

```
singularity exec --bind *input_directory*:/mnt,*output_directory*:/media  --no-home femur-multi-omics:v1.5.0.sif python /tools/register.py -o /media  -inmi mnt/*macsima_stack.tif* \
-mppmi *0.170* -idxmi *0* *4* -markmi mnt/*markers.csv* -inma mnt/*maldi_stack.tif* \
-mppma *5* -idxma *10* -markma mnt/*maldi_markers.csv*
```

See also an example of the implementation above inside a bash script in [coreg.sh](https://github.com/SchapiroLabor/femur-multi-omics/blob/main/coreg.sh).



