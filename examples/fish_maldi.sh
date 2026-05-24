# Specify local path to the fish_and_maldi data
data_dir="C:/MyLocalVolume/fish_and_maldi"
# Specify local path to the output folder
output_dir="C:/MyLocalVolume/output"

fixed_img="${data_dir}/fish.ome.tif"
moving_img="${data_dir}/maldi.tif"

# Example 1
python rami2d-register \
 -fix ${fixed_img} \
 -ifix 1 \
 -mpp-fix 5  \
 -mov ${moving_img} \
 -imov 1 \
 -mpp-mov 15 \
 -o ${output_dir} \
 -mpp-reg 5 \
 -mpp-key 15 \
 -a \
 -rsc 2

# Example 2: try the argument -fl with the flipped moving image

moving_img_flipped="${data_dir}/maldi_flip.tif"

python rami2d-register \
 -fix ${fixed_img} \
 -ifix 1 \
 -mpp-fix 5 \
 -mov ${moving_img_flipped} \
 -imov 1 \
 -mpp-mov 15 \
 -o ${output_dir} \
 -mpp-reg 5 \
 -mpp-key 15 \
 -a \
 -rsc 2 \
 -fl
