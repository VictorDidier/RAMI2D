# The following example illustrates the container execution using the imf_he data set.
# The execution will be done via singularity, the analogous commands for docker are also illustrated but
# commented out.  

# 1) Download the container via singularity or docker
# singularity pull docker://ghcr.io/VictorDidier/rami2d:v1.0.0
#or
# docker pull ghcr.io/VictorDidier/rami2d:v1.0.0

# 2) After downloading the container, specify local path to container file, input_dir and output_dir
container_sif="C:/MyLocalVolume/rami2d_v1.0.0.sif"
#container_docker="C:/MyLocalVolume/rami2d_v1.0.0"
input_dir="C:/MyLocalVolume/data"
output_dir="C:/MyLocalVolume/output"
# 3) names of the images in the input_dir
fixed_img="multiplexed.ome.tif"
moving_img="HE.ome.tif"
annotations="annotations.tif"

# 4a) Sequential execution of register and transform using singularity
singularity exec --bind $input_dir:/mnt,$output_dir:/media --no-home $container_sif rami2d-register \
 -mov /mnt/${moving_img} -imov h -mpp-mov 0.27 \
 -fix /mnt/${fixed_img} -ifix 0 -mpp-fix 0.21 \
 -o /media -mpp-reg 1 -mpp-key 3 -a &&\
 transforms_dir="${output_dir}/qc/fullres_trf" &&\
 singularity exec --bind $input_dir:/mnt,$output_dir:/media,$transforms_dir:/files --no-home $container_sif rami2d-transform \
 -i /mnt/${annotations} -mpp 0.27 -tdir /files -o /media -labels



 # or 4b) Execution via docker

#docker run \
#  -v "$input_dir":/mnt \
#  -v "$output_dir":/media \
#  "$container_sif" \
#  rami2d-register \
#    -mov /mnt/${moving_img} -imov h -mpp-mov 0.27 \
#    -fix /mnt/${fixed_img} -ifix 0 -mpp-fix 0.21 \
#    -o /media -mpp-reg 1 -mpp-key 3 -a && \
#transforms_dir="${output_dir}/qc/fullres_trf" && \
#docker run \
#  -v "$input_dir":/mnt \
#  -v "$output_dir":/media \
#  -v "$transforms_dir":/files \
#  "$container_sif" \
#  rami2d-transform \
#    -i /mnt/${annotations} -mpp 0.27 -tdir /files -o /media -labels

