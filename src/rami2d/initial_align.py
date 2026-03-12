import tifffile as tifff
import numpy as np
from pathlib import Path
from skimage.feature import match_descriptors, plot_matched_features, SIFT
import matplotlib.pyplot as plt
from skimage.transform import EuclideanTransform, AffineTransform,warp
from skimage.exposure import rescale_intensity
from skimage.measure import ransac
from skimage.util import img_as_float32
import itk
import matplotlib.pyplot as plt
from matplotlib.patches import Circle,ConnectionPatch
import os
from itertools import cycle


def keep_first_n_true(bool_list, n=10):
    true_indices = [i for i, val in enumerate(bool_list) if val][:n]
    return [i in true_indices for i in range(len(bool_list))]

def naive_descriptor_matching(fix_arr,mov_arr):
    imgs=[fix_arr,mov_arr]
    descriptor_extractor=SIFT(upsampling=1,n_scales=5)
    keypoints=[]
    descriptors=[]
    for im in imgs:
        descriptor_extractor.detect_and_extract(im)
        keypoints.append(descriptor_extractor.keypoints)
        descriptors.append( descriptor_extractor.descriptors)
    matches=match_descriptors(descriptors[0],
                              descriptors[1],
                              max_ratio=0.6,
                              cross_check=False)

    return keypoints,matches

def ransac_matches(src_coords,dst_coords):
    model=EuclideanTransform()
    if model.estimate(src_coords, dst_coords):
        model_robust, inliers = ransac(
                                        (src_coords, dst_coords),
                                        EuclideanTransform,
                                        min_samples=3,
                                        residual_threshold=2,
                                        max_trials=100,
                                        rng=1,
                                        stop_sample_num=10
                                        )


    #Limit number of ransac matches for displaying in the ransac_matches.png figure
    print("Number of keypoints validated by RANSAC:",np.sum(inliers))
    limit_no=20
    if np.sum(inliers)>limit_no:
        print(f"Only {limit_no} will be displayed in the ransac_matches.png")
        inliers_display=keep_first_n_true(inliers, n=limit_no)
    else:
        inliers_display=inliers

    return model_robust, inliers,inliers_display

def center_of_mass(point_cloud):
    M=len(point_cloud)
    com=np.sum(point_cloud,axis=0)/M
    return com


def conform_trf_object(trf):
    conformed_trf=itk.ParameterObject.New()
    for n in reversed(range(trf.GetNumberOfParameterMaps())):
        conformed_trf.AddParameterMap(trf.GetParameterMap(n))
    return conformed_trf


def save_plot_ransac_matches(array1, array2, positions1, positions2,
                         titles=["Fixed Image","Moving Image"], cmap='gray',
                         circle_radius=0.3,
                         figsize=(14, 6), output_path=None, dpi=300,
                         line_width=1):
    """
    Plot two arrays side by side with connecting lines between corresponding positions.
    Lines cycle through tab20 colormap, and numbers are shown on the first array.

    Parameters:
    array1, array2: 2D numpy arrays
    positions1, positions2: lists of tuples [(row, col), ...] (same length)
    titles: list of two strings for subplot titles
    cmap: colormap for the arrays
    circle_radius: radius of the circular markers
    figsize: tuple for figure size (width, height) in inches
    output_path: path to save the figure (supports .png, .pdf, .svg)
    dpi: resolution for raster formats like PNG
    line_width: width of the connecting lines and circle outlines
    """

    # Set default titles if not provided
    if titles is None:
        titles = ['Array 1', 'Array 2']

    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)

    # Display the arrays - with higher contrast and no interpolation
    im1 = ax1.imshow(array1, cmap=cmap, interpolation='nearest', aspect='equal',
                     origin='upper', vmin=array1.min(), vmax=array1.max())
    im2 = ax2.imshow(array2, cmap=cmap, interpolation='nearest', aspect='equal',
                     origin='upper', vmin=array2.min(), vmax=array2.max())

    # Add colorbars with labels
    cbar1 = plt.colorbar(im1, ax=ax1, fraction=0.046, pad=0.04)
    cbar2 = plt.colorbar(im2, ax=ax2, fraction=0.046, pad=0.04)

    # Set titles
    ax1.set_title(titles[0], fontsize=12, fontweight='bold')
    ax2.set_title(titles[1], fontsize=12, fontweight='bold')

    # Get the shape of arrays to set proper limits
    height1, width1 = array1.shape
    height2, width2 = array2.shape

    # Set axis limits
    ax1.set_xlim(-0.5, width1 - 0.5)
    ax1.set_ylim(height1 - 0.5, -0.5)

    ax2.set_xlim(-0.5, width2 - 0.5)
    ax2.set_ylim(height2 - 0.5, -0.5)

    # Remove grid lines
    ax1.grid(False)
    ax2.grid(False)

    # Get tab20 colormap colors
    tab20 = plt.cm.tab20(np.linspace(0, 1, 20))

    # Draw circles first (with colored outlines)
    for idx, (pos1, pos2) in enumerate(zip(positions1, positions2), start=1):
        # Get color from tab20
        color_idx = (idx - 1) % 20
        circle_color = tab20[color_idx]

        # First array - transparent circle with colored outline
        row1, col1 = pos1
        circle1 = Circle((col1, row1), radius=circle_radius,
                        fill=False, edgecolor=circle_color, linewidth=line_width,
                        zorder=3)
        ax1.add_patch(circle1)

        # Second array - transparent circle with colored outline
        row2, col2 = pos2
        circle2 = Circle((col2, row2), radius=circle_radius,
                        fill=False, edgecolor=circle_color, linewidth=line_width,
                        zorder=3)
        ax2.add_patch(circle2)

    # Draw connecting lines
    for idx, (pos1, pos2) in enumerate(zip(positions1, positions2), start=1):
        # Get color from tab20
        color_idx = (idx - 1) % 20
        line_color = tab20[color_idx]

        row1, col1 = pos1
        row2, col2 = pos2

        # Create a connection patch with specified line width
        con = ConnectionPatch(
            xyA=(col1, row1), coordsA=ax1.transData,
            xyB=(col2, row2), coordsB=ax2.transData,
            color=line_color, linewidth=line_width, alpha=1.0,
            linestyle='dotted', connectionstyle="arc3,rad=0.1",
            zorder=2
        )
        fig.add_artist(con)

    # Add numbers on top (with colored text matching the line/circle)
    for idx, (pos1, _) in enumerate(zip(positions1, positions2), start=1):
        color_idx = (idx - 1) % 20
        text_color = tab20[color_idx]

        row1, col1 = pos1

        # Add number with white background for better visibility
        ax1.text(col1, row1, str(idx), color=text_color,
                ha='right', va='bottom', fontweight='bold', fontsize=5,alpha=0.8,
                bbox=dict(boxstyle="circle,pad=0.2", facecolor='None',
                         edgecolor='none', alpha=0.5),
                zorder=4)

    # Adjust layout
    plt.subplots_adjust(wspace=0.3)

    # Save the figure if output path is provided
    if output_path:
        # Create directory if it doesn't exist
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Save with high quality
        plt.savefig(output_path, dpi=dpi, bbox_inches='tight', facecolor='white')
        print(f"Figure saved to: {output_path}")

    return fig, (ax1, ax2)

def estimate_transformation_parameters(fix_arr,mov_arr,output_ransac_matches=False):
    keypoints,naive_matches=naive_descriptor_matching(fix_arr,mov_arr)
    fix_coords=keypoints[0][naive_matches[:,0]]
    mov_coords=keypoints[1][naive_matches[:,1]]
    ETmodel,inliers,inliers_for_display=ransac_matches(fix_coords,mov_coords)
    matches_ransac=naive_matches[inliers]#indicex of matches validated by ransac algorithm
    theta=-ETmodel.rotation


    if output_ransac_matches:
        matches_ransac_display=naive_matches[inliers_for_display]
        points_fix_display=keypoints[0][matches_ransac_display[:,0]]
        points_mov_display=keypoints[1][matches_ransac_display[:,1]]
        displayed_pairs=list(zip(points_fix_display,points_mov_display))
        displayed_pairs.sort(key=lambda displayed_pairs: displayed_pairs[0][0])  # Sort by y-coordinate of fix points
        points_fix_display, points_mov_display = zip(*displayed_pairs) # sorted keypoints
        save_plot_ransac_matches(fix_arr, mov_arr, points_fix_display, points_mov_display,output_path=output_ransac_matches)

    final_points_fix=keypoints[0][matches_ransac[:,0]]
    final_points_mov=keypoints[1][matches_ransac[:,1]]
    pairs=list(zip(final_points_fix,final_points_mov))
    pairs.sort(key=lambda pair: pair[0][0])  # Sort by y-coordinate of fix points
    final_points_fix, final_points_mov = zip(*pairs) # sorted keypoints

    com_fix=center_of_mass(final_points_fix)
    com_mov=center_of_mass(final_points_mov)
    dy,dx=com_mov-com_fix
    cy,cx=com_mov
    center_of_rotation=[cx,cy]
    displacement=[dx,dy]

    return center_of_rotation,displacement,theta


def create_trf_object(center_of_rotation,displacement,theta,mpp,output_size):
    transforms_dir=Path( os.path.dirname(__file__) ) / "maps" /"transforms"
    translation_template=transforms_dir / "translate.txt"
    rotation_template=transforms_dir / "rotation.txt"
    trf_object=itk.ParameterObject.New()
    #------------------------------------------------
    # ROTATION AROUND CENTER OF MASS OF RANSAC MATCHES
    #-------------------------------------------------
    trf_object.AddParameterFile(str(rotation_template))
    #CenterofRotation arguments are x,y in units with y value in inverted y-axis
    trf_object.SetParameter(0,"CenterOfRotationPoint",[str(val) for val in center_of_rotation ])
    trf_object.SetParameter(0,"TransformParameters", [ str(theta),"0", "0"])#theta,x,y [pos-counterclockwise/neg-clockwise,neg-right/pos-left,neg-down/pos-up]
    trf_object.SetParameter(0,"Size",[str(val) for val in output_size ])
    trf_object.SetParameter(0,"Spacing",[str(mpp),str(mpp)])
    trf_object.SetParameter(0,"Origin",["0","0"])
    #------------------------------------------------
    # TRANSLATION TO OVERLAP CENTER OF MASS OF
    # RANSAC MATCHES IN FIX AND MOV IMAGES
    #-------------------------------------------------
    trf_object.AddParameterFile(str(translation_template))
    trf_object.SetParameter(1,"TransformParameters", [str(val) for val in displacement ])#theta,x,y [pos-counterclockwise/neg-clockwise,neg-right/pos-left,neg-down/pos-up]
    trf_object.SetParameter(1,"Size", [str(val) for val in output_size ])
    trf_object.SetParameter(1,"Spacing",[str(mpp),str(mpp)])
    trf_object.SetParameter(1,"Origin",["0","0"])
    return trf_object

def get_initial_trf(fix_arr,mov_arr,input_mpp,qc_dir,output_dict=None,file_extension=".png"):
    if not output_dict:
        output_mpp=input_mpp
        height,width=fix_arr.shape
        output_dims=[width,height]
    else:
        output_mpp=output_dict["mpp"]
        output_dims=output_dict["xy_dims"]

    #get center_or_rotation(cor),translation parameters (translation) and rotation angle (theta).
    #cor and translation are given in pixels
    outfile_qc=qc_dir / f"ransac_matches{file_extension}"
    center_of_rotation,translation,theta=estimate_transformation_parameters(fix_arr,mov_arr,output_ransac_matches=outfile_qc)
    #transform displacement units  into phyisical space
    center_of_rotation=[ input_mpp*val for val in center_of_rotation ]
    translation=[ input_mpp*val for val in translation ]

    init_trf=create_trf_object(center_of_rotation,translation,theta,output_mpp,output_dims)
    """
    conformed_trf=conform_trf_object(init_trf)
    mov_itk=itk.GetImageFromArray(img_as_float32(mov_arr))
    mov_itk.SetSpacing([mpp,mpp])
    mov_itk_reg=itk.transformix_filter(mov_itk,conformed_trf,log_to_console=False)
    """
    return init_trf
