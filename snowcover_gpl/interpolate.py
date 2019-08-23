import numpy as np
import rasterio
import logging

from os import path
from rasterio.fill import fillnodata
from rasterio.windows import Window
from scipy.ndimage.morphology import binary_closing
from scipy.ndimage import convolve
from scipy.ndimage import label, binary_dilation, sum as ndsum
from collections import Counter

logger = logging.getLogger(__name__)

FLAG_SNOW    = 100
FLAG_NO_SNOW = 0
FLAG_CLOUD   = 205
FLAG_NO_DATA  = 254
MAX_AREA_SIZE_TO_INTERPOLATE = 25

def close(image, value, radius=5, iterations=1):
   mask = (image == value)
   kernel = np.ones( (radius,radius) )
   kernel[radius//2,radius//2] = 0
   closed = binary_closing(mask, structure=kernel, iterations=iterations)
   image[closed] = value
   return image

def closeM(image, mask, value, radius=5, iterations=1):
   kernel = np.ones( (radius,radius) )
   kernel[radius//2,radius//2] = 0
   closed = binary_closing(mask, structure=kernel, iterations=iterations)
   image[closed] = value
   return image

def interpolateSnow(source_raster_path):
   with rasterio.open(source_raster_path) as src:
      im = src.read(1)
   image = im.copy()
   close(image,FLAG_SNOW)
   close(image,FLAG_NO_SNOW)
   return image

def closeSmallGaps(source_raster_path, output_dir):
   with rasterio.open(source_raster_path) as src:
      im = src.read(1)
   image = im.copy()
   logger.info('IMPUTE: Image {} copied to array'.format(source_raster_path))
   mask = im == FLAG_CLOUD
   labels, count = label(mask)
   logger.info('IMPUTE: Firts labels created')
   areas = np.array(ndsum(mask, labels, np.arange(labels.max()+1)))
   new_mask = areas > MAX_AREA_SIZE_TO_INTERPOLATE
   big_clusters = new_mask[labels.ravel()].reshape(labels.shape)
   remove_big_clusters = np.logical_xor(big_clusters, mask)

   closeM(image, remove_big_clusters, FLAG_SNOW)
   closeM(image, remove_big_clusters, FLAG_NO_SNOW)
   
   saveInterpolatedImage(image, source_raster_path, output_dir)


def impute(source_raster_path):
   with rasterio.open(source_raster_path) as src:
      im = src.read(1)
   imputed_array = np.copy(im)
   logger.info('IMPUTE: Image {} copied to array'.format(source_raster_path))
   mask = im == FLAG_CLOUD
   labels, count = label(mask)
   logger.info('IMPUTE: Firts labels created')
   areas = np.array(ndsum(mask, labels, np.arange(labels.max()+1)))
   new_mask = areas > MAX_AREA_SIZE_TO_INTERPOLATE
   big_clusters = new_mask[labels.ravel()].reshape(labels.shape)
   remove_big_clusters = np.logical_xor(big_clusters, mask)
   labels, count = label(remove_big_clusters)
   logger.info('IMPUTE: Big cloud chunks removed and labels created labels created: {} gaps to interpolate'.format(count))
   for idx in range(1, count + 1):
      hole = labels == idx
      logger.info('IMPUTE: starting with label {}'.format(hole))
      surrounding_values = im[binary_dilation(hole) & ~hole]
      most_frequent = Counter(surrounding_values).most_common(1)[0][0]
      imputed_array[hole] = most_frequent
   return imputed_array

def saveInterpolatedImage(image, source_raster_path, ouput_dir):
   FILENAME_OUT = path.join(ouput_dir, 'interpolated_LIS_SEB.TIF')
   with rasterio.open(source_raster_path) as source_image:
      with rasterio.open(FILENAME_OUT, 'w', driver='GTiff', compress='PACKBITS',
                        width=source_image.width, height=source_image.height, count=1,
                        dtype=rasterio.uint8, crs=source_image.crs,
                        transform=source_image.transform) as myraster_out:
         myraster_out.write(image, indexes=1)

def applyInterpolationToRaster(source_raster_path, output_dir):
   image = interpolateSnow(source_raster_path)
   saveInterpolatedImage(image, source_raster_path, output_dir)

def applyImputeToRaster(source_raster_path, output_dir):
   image = impute(source_raster_path)
   saveInterpolatedImage(image, source_raster_path, output_dir)




