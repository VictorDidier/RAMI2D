import numpy as np
from skimage.feature import SIFT, match_descriptors
from skimage.transform import ProjectiveTransform
from skimage.measure import ransac
from skimage.util import img_as_float32, img_as_ubyte
from skimage.color import gray2rgb
from skimage.draw import disk
from skimage.io import imsave
from skimage.transform import AffineTransform  # Added for transform operations
from scipy.spatial import cKDTree
from typing import Tuple, List, Optional
import warnings
import os
from matplotlib import pyplot as plt
import matplotlib

def robust_feature_matching(
    image1: np.ndarray,
    image2: np.ndarray,
    n_features: int = 50,
    min_matches: int = 4,
    use_ransac: bool = True,
    ransac_threshold: float = 3.0,
    output_dir: Optional[str] = None,
    output_prefix: str = "matched_features"
) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]], Optional[np.ndarray], List[float]]:
    """
    Robust feature matching between two images (8-bit or 16-bit).

    Parameters:
    -----------
    image1, image2 : np.ndarray
        Input images (grayscale, 8-bit or 16-bit)
    n_features : int
        Number of top-ranked features to return
    min_matches : int
        Minimum number of matches required for RANSAC
    use_ransac : bool
        Whether to use RANSAC for outlier removal
    ransac_threshold : float
        RANSAC threshold in pixels
    output_dir : str, optional
        Directory to save visualization images
    output_prefix : str
        Prefix for output filenames

    Returns:
    --------
    centers1 : List of (x, y) coordinates for image1
    centers2 : List of (x, y) coordinates for image2
    transformation_matrix : Estimated transform (None if insufficient matches)
    similarity_scores : Similarity scores for matched features
    """

    # Convert images to appropriate format
    img1_float = prepare_image(image1)
    img2_float = prepare_image(image2)

    # Step 1: Detect and extract features using SIFT
    kp1, desc1, scales1 = extract_sift_features(img1_float)
    kp2, desc2, scales2 = extract_sift_features(img2_float)

    if len(kp1) == 0 or len(kp2) == 0:
        warnings.warn("Insufficient features detected in one or both images")
        return [], [], None, []

    # Step 2: Match features with multiple strategies
    matches, similarity_scores = match_features_with_ranking(
        desc1, desc2, kp1, kp2, scales1, scales2
    )

    if len(matches) < min_matches:
        warnings.warn(f"Only {len(matches)} matches found (minimum: {min_matches})")
        return [], [], None, []

    # Step 3: Apply RANSAC for robust matching
    if use_ransac and len(matches) >= min_matches:
        robust_matches, transform = apply_ransac_filtering(
            matches, kp1, kp2, ransac_threshold, min_matches
        )
        matches = robust_matches
    else:
        transform = None

    # Step 4: Get top n features by similarity score
    top_matches = get_top_matches(matches, similarity_scores, n_features)

    # Step 5: Extract center coordinates
    centers1, centers2 = extract_match_coordinates(top_matches, kp1, kp2)

    # Step 6: Create visualization if output directory is provided
    if output_dir is not None:
        os.makedirs(output_dir, exist_ok=True)

        # Get top n matches for visualization
        n_viz = min(n_features, len(top_matches))
        top_matches_viz = top_matches[:n_viz]
        centers1_viz = centers1[:n_viz]
        centers2_viz = centers2[:n_viz]

        # Create overlay images
        overlay1 = create_feature_overlay(
            image1, centers1_viz,
            scores=similarity_scores[:n_viz] if len(similarity_scores) >= n_viz else None
        )

        overlay2 = create_feature_overlay(
            image2, centers2_viz,
            scores=similarity_scores[:n_viz] if len(similarity_scores) >= n_viz else None
        )

        # Save overlay images
        save_path1 = os.path.join(output_dir, f"{output_prefix}_image1_overlay.png")
        save_path2 = os.path.join(output_dir, f"{output_prefix}_image2_overlay.png")

        imsave(save_path1, overlay1)
        imsave(save_path2, overlay2)

        print(f"Overlay images saved to:")
        print(f"  Image 1: {save_path1}")
        print(f"  Image 2: {save_path2}")

        # Also create a side-by-side comparison
        create_comparison_overlay(
            image1, image2, centers1_viz, centers2_viz,
            output_dir, output_prefix
        )

    return centers1, centers2, transform, similarity_scores[:len(top_matches)]


def create_feature_overlay(
    image: np.ndarray,
    centers: List[Tuple[float, float]],
    scores: Optional[List[float]] = None,
    circle_radius: int = 15,
    circle_thickness: int = 3,
    text_offset: Tuple[int, int] = (-25, 5)
) -> np.ndarray:
    """
    Create an overlay image with ranked feature circles and numbers.

    Parameters:
    -----------
    image : np.ndarray
        Input grayscale image
    centers : List[Tuple[float, float]]
        List of (x, y) center coordinates
    scores : List[float], optional
        Similarity scores for coloring
    circle_radius : int
        Radius of circles in pixels
    circle_thickness : int
        Thickness of circle border
    text_offset : Tuple[int, int]
        Offset for text placement relative to circle center

    Returns:
    --------
    overlay : np.ndarray
        RGB image with feature overlays
    """

    # Convert grayscale to RGB for coloring
    if len(image.shape) == 2:
        overlay = gray2rgb(image)
    else:
        overlay = image.copy()

    # Normalize image to 0-255 for display
    if overlay.dtype == np.uint16:
        overlay = (overlay / 65535 * 255).astype(np.uint8)
    elif overlay.dtype != np.uint8:
        overlay = (overlay * 255).astype(np.uint8)

    # Make sure overlay is 8-bit RGB
    if overlay.dtype != np.uint8:
        overlay = (overlay * 255).astype(np.uint8)

    # Create a matplotlib figure for text rendering
    dpi = 100
    fig_width = overlay.shape[1] / dpi
    fig_height = overlay.shape[0] / dpi

    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi)
    ax.imshow(overlay)
    ax.axis('off')

    # Draw circles and numbers for each feature
    for idx, (x, y) in enumerate(centers):
        rank = idx + 1

        # Convert coordinates to integers for drawing
        x_int, y_int = int(round(x)), int(round(y))

        # Create circle using skimage's disk function
        rr, cc = disk((y_int, x_int), circle_radius, shape=overlay.shape[:2])

        # Draw red circle border (multiple circles for thickness)
        for r_offset in range(-circle_thickness//2, circle_thickness//2 + 1):
            rr_thick, cc_thick = disk((y_int, x_int), circle_radius + r_offset,
                                      shape=overlay.shape[:2])
            # Set circle to red
            overlay[rr_thick, cc_thick, 0] = 255  # Red channel
            overlay[rr_thick, cc_thick, 1] = 0    # Green channel
            overlay[rr_thick, cc_thick, 2] = 0    # Blue channel

        # Add rank number to the left of the circle
        text_x = x_int + text_offset[0]
        text_y = y_int + text_offset[1]

        # Add text using matplotlib (better quality than PIL)
        ax.text(
            text_x, text_y,
            str(rank),
            fontsize=12,
            fontweight='bold',
            color='red',
            ha='center',
            va='center',
            bbox=dict(
                boxstyle='circle,pad=0.3',
                facecolor='white',
                edgecolor='red',
                linewidth=1.5
            )
        )

    # Update the image with matplotlib text
    fig.canvas.draw()

    # Convert matplotlib figure to numpy array
    overlay_with_text = np.array(fig.canvas.renderer.buffer_rgba())
    overlay_with_text = overlay_with_text[:, :, :3]  # Remove alpha channel

    plt.close(fig)

    return overlay_with_text


def create_comparison_overlay(
    image1: np.ndarray,
    image2: np.ndarray,
    centers1: List[Tuple[float, float]],
    centers2: List[Tuple[float, float]],
    output_dir: str,
    output_prefix: str,
    circle_radius: int = 15,
    text_offset: Tuple[int, int] = (-25, 5)
) -> None:
    """
    Create a side-by-side comparison of matched features.
    """

    # Create overlays for both images
    overlay1 = create_feature_overlay(
        image1, centers1,
        circle_radius=circle_radius,
        text_offset=text_offset
    )

    overlay2 = create_feature_overlay(
        image2, centers2,
        circle_radius=circle_radius,
        text_offset=text_offset
    )

    # Create side-by-side comparison
    if overlay1.shape != overlay2.shape:
        # Resize to match dimensions (use smallest dimensions)
        min_height = min(overlay1.shape[0], overlay2.shape[0])
        min_width = min(overlay1.shape[1], overlay2.shape[1])
        overlay1 = overlay1[:min_height, :min_width]
        overlay2 = overlay2[:min_height, :min_width]

    # Create comparison image
    comparison = np.hstack([overlay1, overlay2])

    # Add separation line and labels
    height, width = comparison.shape[:2]

    # Add vertical separation line
    sep_line_width = 3
    sep_x = overlay1.shape[1]
    comparison[:, sep_x-sep_line_width//2:sep_x+sep_line_width//2+1] = [255, 255, 255]

    # Create figure for adding labels
    dpi = 100
    fig_width = comparison.shape[1] / dpi
    fig_height = comparison.shape[0] / dpi + 0.5  # Extra space for title

    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi)
    ax.imshow(comparison)
    ax.axis('off')

    # Add title and image labels
    ax.set_title(f"Feature Matching Comparison - {len(centers1)} Top Matches",
                 fontsize=14, fontweight='bold', pad=20)

    # Add image labels
    ax.text(overlay1.shape[1]//2, overlay1.shape[0] + 40,
            "Image 1", ha='center', va='center',
            fontsize=12, fontweight='bold')
    ax.text(overlay1.shape[1] + overlay2.shape[1]//2,
            overlay2.shape[0] + 40,
            "Image 2", ha='center', va='center',
            fontsize=12, fontweight='bold')

    # Add legend for numbering
    ax.text(10, overlay1.shape[0] + 20,
            "Numbers indicate feature rank (1 = most similar)",
            fontsize=10, color='red',
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

    # Adjust layout and save
    plt.tight_layout()
    save_path = os.path.join(output_dir, f"{output_prefix}_comparison.png")
    plt.savefig(save_path, dpi=150, bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)

    print(f"  Comparison: {save_path}")


def prepare_image(image: np.ndarray) -> np.ndarray:
    """Prepare image for feature extraction."""
    # Convert to float32 for SIFT
    img_float = img_as_float32(image)

    # Normalize based on bit depth
    if image.dtype == np.uint16:
        # Normalize 16-bit to [0, 1] range
        img_float = img_float / 65535.0
    elif image.dtype == np.uint8:
        # Already normalized by img_as_float32
        pass

    # Apply mild contrast enhancement
    p_low, p_high = np.percentile(img_float, [2, 98])
    img_float = np.clip((img_float - p_low) / (p_high - p_low), 0, 1)

    return img_float


def extract_sift_features(image: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extract SIFT features from image."""
    detector = SIFT(
        n_octaves=4,
        n_scales=3,
        sigma_min=1.6,
        c_edge=10.0,
        upsampling=1
    )

    detector.detect_and_extract(image)

    keypoints = detector.keypoints
    descriptors = detector.descriptors
    scales = detector.scales

    # Convert keypoints to (x, y) format
    keypoints_xy = np.column_stack([keypoints[:, 1], keypoints[:, 0]])

    return keypoints_xy, descriptors, scales


def match_features_with_ranking(
    desc1: np.ndarray,
    desc2: np.ndarray,
    kp1: np.ndarray,
    kp2: np.ndarray,
    scales1: np.ndarray,
    scales2: np.ndarray,
    max_ratio: float = 0.75
) -> Tuple[np.ndarray, np.ndarray]:
    """Match features and rank by similarity."""

    # Strategy 1: Brute force matching with ratio test
    matches_ratio, scores_ratio = ratio_test_matching(
        desc1, desc2, max_ratio=max_ratio
    )

    # Strategy 2: Cross-check matching
    matches_cross, scores_cross = cross_check_matching(desc1, desc2)

    # Strategy 3: Spatial consistency
    matches_spatial, scores_spatial = spatial_consistency_matching(
        desc1, desc2, kp1, kp2, scales1, scales2
    )

    # Combine matches
    all_matches = []
    all_scores = []

    for (i, j), score in zip(matches_ratio, scores_ratio):
        all_matches.append((i, j))
        all_scores.append(score)

    for (i, j), score in zip(matches_cross, scores_cross):
        if (i, j) not in all_matches:
            all_matches.append((i, j))
            all_scores.append(score)

    for (i, j), score in zip(matches_spatial, scores_spatial):
        if (i, j) not in all_matches:
            all_matches.append((i, j))
            all_scores.append(score)

    # Convert to numpy arrays and sort
    if len(all_matches) > 0:
        matches_array = np.array(all_matches)
        scores_array = np.array(all_scores)

        sorted_indices = np.argsort(-scores_array)
        matches_array = matches_array[sorted_indices]
        scores_array = scores_array[sorted_indices]
    else:
        matches_array = np.empty((0, 2), dtype=int)
        scores_array = np.empty(0, dtype=float)

    return matches_array, scores_array


def ratio_test_matching(
    desc1: np.ndarray,
    desc2: np.ndarray,
    max_ratio: float = 0.75
) -> Tuple[np.ndarray, np.ndarray]:
    """Ratio test matching."""
    if len(desc1) == 0 or len(desc2) == 0:
        return np.empty((0, 2), dtype=int), np.empty(0, dtype=float)

    tree2 = cKDTree(desc2)

    matches = []
    scores = []

    for i, d1 in enumerate(desc1):
        distances, indices = tree2.query(d1, k=2, p=2)

        if distances[0] < max_ratio * distances[1]:
            similarity = 1.0 / (1.0 + distances[0])
            matches.append((i, indices[0]))
            scores.append(similarity)

    return np.array(matches, dtype=int), np.array(scores)


def cross_check_matching(
    desc1: np.ndarray,
    desc2: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """Cross-check matching."""
    if len(desc1) == 0 or len(desc2) == 0:
        return np.empty((0, 2), dtype=int), np.empty(0, dtype=float)

    tree1 = cKDTree(desc1)
    tree2 = cKDTree(desc2)

    matches = []
    scores = []

    forward_matches = {}
    for i, d1 in enumerate(desc1):
        dist, idx = tree2.query(d1, k=1, p=2)
        forward_matches[i] = (idx, dist)

    for j, d2 in enumerate(desc2):
        dist, idx = tree1.query(d2, k=1, p=2)

        if forward_matches.get(idx, (None, None))[0] == j:
            dist_fwd = forward_matches[idx][1]
            dist_bwd = dist
            avg_distance = (dist_fwd + dist_bwd) / 2.0
            similarity = 1.0 / (1.0 + avg_distance)

            matches.append((idx, j))
            scores.append(similarity)

    return np.array(matches, dtype=int), np.array(scores)


def spatial_consistency_matching(
    desc1: np.ndarray,
    desc2: np.ndarray,
    kp1: np.ndarray,
    kp2: np.ndarray,
    scales1: np.ndarray,
    scales2: np.ndarray,
    spatial_weight: float = 0.3
) -> Tuple[np.ndarray, np.ndarray]:
    """Spatial consistency matching."""
    if len(desc1) == 0 or len(desc2) == 0:
        return np.empty((0, 2), dtype=int), np.empty(0, dtype=float)

    matches_desc, scores_desc = ratio_test_matching(desc1, desc2)

    if len(matches_desc) == 0:
        return matches_desc, scores_desc

    spatial_scores = []
    for (i, j) in matches_desc:
        scale_sim = 1.0 / (1.0 + abs(scales1[i] - scales2[j]))
        spatial_score = scale_sim

        combined_score = (1 - spatial_weight) * scores_desc[len(spatial_scores)] + \
                        spatial_weight * spatial_score

        spatial_scores.append(combined_score)

    return matches_desc, np.array(spatial_scores)


def apply_ransac_filtering(
    matches: np.ndarray,
    kp1: np.ndarray,
    kp2: np.ndarray,
    threshold: float,
    min_samples: int
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """Apply RANSAC for outlier removal."""
    if len(matches) < min_samples:
        return matches, None

    src_pts = kp1[matches[:, 0]]
    dst_pts = kp2[matches[:, 1]]

    try:
        # Use ransac from skimage.measure
        model, inliers = ransac(
            (src_pts, dst_pts),
            ProjectiveTransform,
            min_samples=min_samples,
            residual_threshold=threshold,
            max_trials=1000,
            stop_sample_num=100,
            stop_residual_sum=0.1,
            stop_probability=0.99
        )

        if inliers is not None:
            inlier_matches = matches[inliers]
            return inlier_matches, model.params
        else:
            return matches, None

    except Exception as e:
        warnings.warn(f"RANSAC failed: {e}")
        return matches, None


def get_top_matches(
    matches: np.ndarray,
    scores: np.ndarray,
    n: int
) -> np.ndarray:
    """Get top n matches by similarity score."""
    n_valid = min(n, len(matches))
    if n_valid == 0:
        return np.empty((0, 2), dtype=int)

    if len(scores) < len(matches):
        default_scores = np.ones(len(matches))
        default_scores[:len(scores)] = scores
        scores = default_scores

    sorted_indices = np.argsort(-scores)[:n_valid]
    return matches[sorted_indices]


def extract_match_coordinates(
    matches: np.ndarray,
    kp1: np.ndarray,
    kp2: np.ndarray
) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """Extract coordinates of matched features."""
    centers1 = []
    centers2 = []

    for i, j in matches:
        if i < len(kp1) and j < len(kp2):
            x1, y1 = kp1[i]
            x2, y2 = kp2[j]
            centers1.append((float(x1), float(y1)))
            centers2.append((float(x2), float(y2)))

    return centers1, centers2


# Simplified example usage without problematic imports
def example_usage_simple():
    """Simple example usage with synthetic images."""
    import matplotlib.pyplot as plt

    # Create test directory for outputs
    test_dir = "feature_matching_output"
    os.makedirs(test_dir, exist_ok=True)

    # Create synthetic test images
    print("Creating synthetic test images...")

    np.random.seed(42)
    img_size = 512

    # Create first image with clear features
    img1 = np.zeros((img_size, img_size), dtype=np.uint16)

    # Add bright features (squares)
    features = [
        (100, 150), (200, 300), (350, 400), (450, 100),
        (120, 400), (300, 200), (400, 350), (250, 450)
    ]

    for x, y in features:
        size = 15
        y_start = max(0, y - size)
        y_end = min(img_size, y + size)
        x_start = max(0, x - size)
        x_end = min(img_size, x + size)
        img1[y_start:y_end, x_start:x_end] = 50000  # Bright value for 16-bit

    # Create second image with slight transformation
    img2 = np.zeros_like(img1)

    # Shift features slightly
    shift_x, shift_y = 10, -8
    for x, y in features:
        new_x, new_y = x + shift_x, y + shift_y
        if 0 <= new_x < img_size and 0 <= new_y < img_size:
            size = 15
            y_start = max(0, new_y - size)
            y_end = min(img_size, new_y + size)
            x_start = max(0, new_x - size)
            x_end = min(img_size, new_x + size)
            img2[y_start:y_end, x_start:x_end] = 50000

    # Add some noise
    noise = np.random.normal(0, 1000, img1.shape).astype(np.int32)
    img1 = np.clip(img1.astype(np.int32) + noise, 0, 65535).astype(np.uint16)
    img2 = np.clip(img2.astype(np.int32) + noise, 0, 65535).astype(np.uint16)

    print("Running feature matching with visualization...")

    # Run feature matching with visualization
    centers1, centers2, transform, scores = robust_feature_matching(
        img1, img2,
        n_features=8,
        min_matches=3,
        use_ransac=True,
        ransac_threshold=10.0,
        output_dir=test_dir,
        output_prefix="test_match"
    )
    print("centers1",len(centers1))
    print("centers2",len(centers2))
    print(f"\nResults:")
    print(f"Found {len(centers1)} feature matches")

    if len(centers1) > 0:
        print(f"\nFeature centers in image 1:")
        for i, (x, y) in enumerate(centers1):
            score_str = f" - Score: {scores[i]:.3f}" if i < len(scores) else ""
            print(f"  Rank {i+1}: ({x:.1f}, {y:.1f}){score_str}")

        print(f"\nCorresponding centers in image 2:")
        for i, (x, y) in enumerate(centers2):
            print(f"  Rank {i+1}: ({x:.1f}, {y:.1f})")

    if transform is not None:
        print(f"\nEstimated transformation matrix:")
        print(transform)

    print(f"\nVisualization saved to directory: {test_dir}")

    # Display the results
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Load and display saved images
    overlay1_path = os.path.join(test_dir, "test_match_image1_overlay.png")
    overlay2_path = os.path.join(test_dir, "test_match_image2_overlay.png")
    comparison_path = os.path.join(test_dir, "test_match_comparison.png")

    if os.path.exists(overlay1_path):
        overlay1 = plt.imread(overlay1_path)
        axes[0].imshow(overlay1)
        axes[0].set_title("Image 1 with Features")
        axes[0].axis('off')

    if os.path.exists(overlay2_path):
        overlay2 = plt.imread(overlay2_path)
        axes[1].imshow(overlay2)
        axes[1].set_title("Image 2 with Features")
        axes[1].axis('off')

    if os.path.exists(comparison_path):
        comparison = plt.imread(comparison_path)
        axes[2].imshow(comparison)
        axes[2].set_title("Feature Matching Comparison")
        axes[2].axis('off')
    else:
        # Create a simple comparison if file doesn't exist
        axes[2].text(0.5, 0.5, "Comparison image\nwould be here",
                    ha='center', va='center', transform=axes[2].transAxes)
        axes[2].axis('off')

    plt.tight_layout()
    plt.show()

    return centers1, centers2, scores