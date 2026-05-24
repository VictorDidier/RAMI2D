# Specify local path to the imf_and_he data
data_dir="C:/MyLocalVolume/imf_and_he"
# Specify local path to the output folder
output_dir="C:/MyLocalVolume/output"

fixed_img="${data_dir}/multiplexed.ome.tif"
moving_img="${data_dir}/HE.ome.tif"

#Example 1: register the H&E image to the imf
python rami2d-register -mov ${moving_img} -imov h -mpp-mov 0.27 -fix ${fixed_img} -ifix 0 -mpp-fix 0.21 -o ${output_dir} -mpp-reg 1 -mpp-key 3 -a

#Example 2: register the annotations made on the H&E images using rami2d-transform
annotations="${data_dir}/annotations.tif"
transforms_dir="${output_dir}/qc/fullres_trf"

python rami2d-transform -i ${annotations} -mpp 0.27 -tdir ${transforms_dir} -o ${output_dir} -labels


