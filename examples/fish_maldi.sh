python -m rami2d.register \
-fix "fish.ome.tif" \
-ifix 1 \
-mpp-fix 5  \
-mov "maldi.tif" \
-imov 1 \
-mpp-mov 15 \
-o "fish_and_maldi" \
-mpp-reg 5 \
-mpp-key 15 \
-a \
-rsc 2

# or

python -m rami2d.register \
-fix "fish.ome.tif" \
-ifix 1 \
-mpp-fix 5  \
-mov "maldi_flip.tif" \
-imov 1 \
-mpp-mov 15 \
-o "fish_and_maldi" \
-mpp-reg 5 \
-mpp-key 15 \
-a \
-rsc 2 \
-fl 

