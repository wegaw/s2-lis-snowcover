import numpy as np
import rasterio
import logging
import cv2


from os import path
from scipy.ndimage import label, sum as ndsum

logger = logging.getLogger(__name__)

FLAG_SNOW    = 100
FLAG_NO_SNOW = 0
FLAG_CLOUD   = 205
FLAG_NO_DATA  = 254

FLAG_CLOUD_INPAINT = 20
FLAG_ND_INPAINT = 1
FLAG_NS_INPAINT = 10
FLAG_SNOW_INPAINT = 255
INTERPOLATION_THRESHOLD = 122

MAX_AREA_SIZE_TO_INTERPOLATE = 25

def opencvInpaint(data, mask):
   # ND=0--NS=10--C=20---------------------S=255
   # Change pixel values to get a better interpolation
   data[data==FLAG_CLOUD] = FLAG_CLOUD_INPAINT
   data[data==FLAG_NO_SNOW] = FLAG_NS_INPAINT
   data[data==FLAG_NO_DATA] = FLAG_ND_INPAINT
   data[data==FLAG_SNOW] = FLAG_SNOW_INPAINT
   maskCV = np.array(mask).astype(np.uint8)

   # we use cd2.INPAINT_NS because it is faster for our data
   dst = cv2.inpaint(data,maskCV,5,cv2.INPAINT_NS)

   # Round values to SNOW or NO_SNOW
   dst[np.logical_and(mask,dst<=INTERPOLATION_THRESHOLD)] = FLAG_NS_INPAINT
   dst[np.logical_and(mask,dst>INTERPOLATION_THRESHOLD)] = FLAG_SNOW_INPAINT

   # Put back the original flag values
   # Attention to the order (if no data is not before no snow, values are mixed)
   dst[dst==FLAG_ND_INPAINT] = FLAG_NO_DATA
   dst[dst==FLAG_CLOUD_INPAINT] = FLAG_CLOUD
   dst[dst==FLAG_NS_INPAINT] = FLAG_NO_SNOW
   dst[dst==FLAG_SNOW_INPAINT] = FLAG_SNOW

   return dst

def closeSmallGaps(source_raster_path, output_dir):
   # Read the image
   with rasterio.open(source_raster_path) as src:
      im = src.read(1)
   image = im.copy()
   logger.debug('Creating small cloud mask')
   # Create a cloud mask
   mask = im == FLAG_CLOUD
   labels, count = label(mask)
   areas = np.array(ndsum(mask, labels, np.arange(labels.max()+1)))
   # identify the clusters bigger than the ones that we want to interpolate
   new_mask = areas > MAX_AREA_SIZE_TO_INTERPOLATE
   big_clusters = new_mask[labels.ravel()].reshape(labels.shape)
   # Reverse the new mask so we get the small cloud mask
   small_cluster_mask = np.logical_xor(big_clusters, mask)
   logger.debug('Small cloud mask created')
   
   logger.debug('Applying inpainting algorithm')
   # Apply OpenCV's inpaint algorithm to the image in so it fills the small clouds
   image=opencvInpaint(image,small_cluster_mask)
   
   logger.debug('Saving the image')
   # Save the image in the same output directory
   saveInterpolatedImage(image, source_raster_path, output_dir)


def saveInterpolatedImage(image, source_raster_path, ouput_dir):
   FILENAME_OUT = path.join(ouput_dir, 'interpolated_LIS_SEB.TIF')
   with rasterio.open(source_raster_path) as source_image:
      with rasterio.open(FILENAME_OUT, 'w', driver='GTiff', compress='PACKBITS',
                        width=source_image.width, height=source_image.height, count=1,
                        dtype=rasterio.uint8, crs=source_image.crs,
                        transform=source_image.transform) as myraster_out:
         myraster_out.write(image, indexes=1)





