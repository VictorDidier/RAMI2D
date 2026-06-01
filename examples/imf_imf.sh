# Specify local path to the imf_and_imf data
data_dir="C:/MyLocalVolume/imf_and_imf"
# Specify local path to the output folder
output_dir="C:/MyLocalVolume/output"

fixed_img="${data_dir}/imf_timepoint1.ome.tif"
moving_img="${data_dir}/imf_timepoint2.ome.tif"


rami2d-register -fix ${fixed_img} -ifix 0 -mpp-fix 2 -mov ${moving_img} -imov 1 -mpp-mov 2 -o ${output_dir} -mpp-reg 2 -mpp-key 3 -a 