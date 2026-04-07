![Logo](https://github.com/VictorDidier/RAMI2D/blob/main/data/figs/logo2.png)
# DESCRIPTION

(RAMI2D) Robust Alignment of Multichannel Images in 2D is a command-line interface tool that allows the registration of multi-channel images in a convenient way by exposing multiple parameters that control the registration output. The convenience that RAMI2D provides is an easy interface to carry out the registration of multi-channel images via [itk-elastix](https://github.com/InsightSoftwareConsortium/ITKElastix).  RAMI2D offers 3 pre-defined registration schemes: 1) Rigid, 2) Rigid+Affine 3) Rigid+Affine+Bsplines, each of them providing more geometrical adaptability and thus more control in the final outcome.  If the initial images are very missaligned, e.g. rotated in large angles or partially overlapping fields of view, we provide an option to estimate an initial alignment by finding keypoints via SIFT and RANSAC algorithms. These keypoints are used to construct an itk transformation map that is ingested as an initial alignment to the pre-defined registration schemes.

Among others, one of the advantages of using [itk-elastix](https://github.com/InsightSoftwareConsortium/ITKElastix) is that it renders registration results not only as an image but also as a set of transformation parameters that can be later used for registering images associated to the moving data, e.g. concurrent acquisitions or  segmentation masks.

RAMI2D offers the following features:

# Features overview
- **Supported input formats:** multi-channel grayscale and single-page RGB images saved as ome.tif,tif or any format supported by [OpenSlide](https://openslide.org/).
- **Multimodal registration:** different microscopy modalities can be registered, H&E,Fluorescence, MALDI, whatever produces pixels in the formats mentioned above.
- **Multi-scale:** Fixed and moving images can have different resolutions.
- **Registration of consecutive slices**.
- **Multi-step registration scheme:** Scheme-1) Rigid, Scheme-2) Rigid->Affine, Scheme-3)Rigid->Affine->Bsplines.
- **Outputs:** a registered image saved as pyramidal ome.tif, transformation parameters as.txt files, figure with keypoints matches, low-resolution preview of registration results.
- **Test mode:** check intermediate results in low-resolution before applying them to the full-resolution image and all its channels.

# Flowchart
The flowchart below shows how the tool processes the images, this workflow is the usual footprint of a registration process and similarly can be found in tools like [RegisterVirtualSlices](https://github.com/fiji/register_virtual_stack_slices) or [palom](https://github.com/labsyspharm/palom).  The initial alignment via SIFT and RANSAC is a standard and was firstly shown by Brown, Matthew, and David G. Lowe in  ["Recognising panoramas"](https://doi.org/10.1109/ICCV.2003.1238630).

![Flowchart](https://github.com/VictorDidier/RAMI2D/blob/main/data/figs/flowchart-horizontal-annotations.png)

# Use cases
* H&E registered to multichannel immunofluorescence image:
![he_imf](https://github.com/VictorDidier/RAMI2D/blob/main/data/figs/UseCase_01.png)
* MALDI data registered to FISH image:
![fish_maldi](https://github.com/VictorDidier/RAMI2D/blob/main/data/figs/fish_maldi2.png)

# Quick guide
### CLI
* Required arguments: -fix, -mpp-fix, -ifix, -mov, -mpp-mov, -imov, -mpp-reg, -o
* Optional arguments: -a, -fl, -mpp-key, -rsc, -gs, -fn, -pl, -comp, -m, -test
### Input files
* any file with formats .tif, .ome.tif, or supported by [openslide](https://openslide.org/formats/).
### Output files
* registered image as pyramidal .ome.tif.
* qc_reg directory with three folders: keypoints, fullres_trf and refchns.
### Examples
* [sample_images] (https://github.com/VictorDidier/RAMI2D/tree/main/data/samples) and its corresponding
[cli_arguments](https://github.com/VictorDidier/RAMI2D/tree/main/examples) as .sh files.
* [JupyterNotebook] (https://github.com/VictorDidier/RAMI2D/blob/main/examples/apply_transform_to_labels.ipynb).



# TERMS
- fixed image: image to register against.
- moving image: image that will be transformed to match the structures and dimensions of the fixed image.
- mpp: microns per pixel, i.e. pixel size in micrometers.
- transformation map: set of parameters that define one or multiple geometrical transformations (Rigid,Translation,Affine, etc.).
- registration map: set of parameters that define how the registration between fixed and moving images will be carried out,e.g. pixel sampling, interpolation order, output bit-depth, transformation, etc.

# CLI description
The main script is ./src/rami2d/register.py.
To visualize the documentation for each argument in your terminal, go to the ./src folder and run the following command
```
python -m rami2d.register --help
```

### Fixed image arguments
| Argument|Type|Description|Default value|Required|
|---------|----|-----------|-------------|-------------|
| -fix    | Path | path to fix image  | NA |True|
| -mpp-fix| float | pixel-size in micrometers| NA |True|
|-ifix    | integer or string h,e,d | if integer then 0-based index of channel to be used for registration. If string Hematoxylin, Eosin or DAB|NA|True|

### Moving image arguments
| Argument|Type|Description|Default value|Required|
|---------|----|-----------|-------------|-------------|
| -mov    | Path | path to fix image  | NA |True|
| -mpp-mov| float | pixel-size in micrometers| NA |True|
|-imov    | integer or string h,e,d | if integer then 0-based index of channel to be used for registration. If string Hematoxylin, Eosin or DAB|NA|True|

### Registration arguments
| Argument|Type|Description|Default value|Required|
|---------|----|-----------|-------------|-------------|
| -a     | Boolean flag | Implement initial alignent by finding keypoints | NA |False|
| -fl    | Boolean flag | Flip moving image in case is mirrored respect to the fix image| NA |False|
| -mpp-key | float | image resolution in micrometers to be used for searching keypoints | NA |False|
| -mpp-reg | float | image resolution in micrometers to be used for applying the registration scheme | NA |True|
| -rsc | integer | Select one of the following registration schemes 1,2,3,check the list in features section | 1 |False|
| -gs | two integers | x y size of grid to be used in bsplines in micrometers (only applicable when -rsc 3) | 1000 1000 |False|

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
### via a conda environment
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
- (5) Go to the directory ./src:
```
cd ./src
```
- (6) check if package and environment are working correctly by calling the CLI documentation:
```
python -m rami2d.register --help
```
- (7) run register.py with your arguments, you can check the sample data and its corresponding arguments.

### via container

**Singularity**
Upcoming!

**Docker**
Upcoming!

# Data sources
1) imf_imf: Data available on Synapse: https://www.synapse.org/Synapse:syn51449054
from Wünnemann, F., Sicklinger, F., Bestak, K. et al. Spatial multiomics of acute myocardial infarction reveals immune cell infiltration through the endocardium. Nat Cardiovasc Res 4, 1345-1362 (2025). https://doi.org/10.1038/s44161-025-00717-y.

 2) fish_maldi:Data was collected by Dr. Veronika Saharuka (Metabolomics Core Technology Platform, Heidelberg University) and Dr. James Cleland (Division of Regulatory Genomics and Cancer Evolution, DKFZ).

 3) he_imf: modified from https://www.10xgenomics.com/datasets/xenium-ffpe-human-breast-biomarkers.
 
 # Acknowledgements
 This tool developed during my time in the [SchapiroLab](https://www.schapirolab.com/) in Heidelberg – I'm grateful for the opportunity and setting that made it possible.


