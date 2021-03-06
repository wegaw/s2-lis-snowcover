from __future__ import absolute_import

from celery.utils.log import get_task_logger
from celery import task
from .celery import app as celery_app

logger = get_task_logger(__name__)

import os
import subprocess
import zipfile
import json
from shutil import rmtree, make_archive, move
from .storage_manager import GoogleStorageManager
from .interpolate import closeSmallGaps

with open(os.environ['CONFIGURATION']) as config_file:
    data = json.load(config_file)

SCENE_BUCKET = data['SCENE_BUCKET']
SCENE_L1C_FOLDER= data['SCENE_L1C_FOLDER']
SCENE_L2A_FOLDER = data['SCENE_L2A_FOLDER']
SCENE_LIS_FOLDER = data['SCENE_LIS_FOLDER']
SCENE_DISCARDED_FOLDER = data['SCENE_DISCARDED_FOLDER']
DATAFOLDER = data['DATAFOLDER']
DEM_PATH = data['DEM_PATH']
MAX_RAM = data['MAX_RAM']
MAX_THREADS = data['MAX_THREADS']
LIS_OUTPUT_PATH = data['LIS_OUTPUT_PATH']
LIS_PRODUCTS_PATH = data['LIS_PRODUCTS_PATH']
LIS_OUTPUT_RASTER = data['LIS_OUTPUT_RASTER']
DEFAULT_RETRY_COUNTDOWN = 5 
DEFAULT_MAX_RETRIES = 5

IGNORE_SCENE_CLOUD_THRESHOLD = 90


'''
   BASIC SEN2COR FLOW
   1. Download input data (from input parameter) to <L1C image path>
   2. Unzip to <unzipped>
      a. remove downloaded file
   3. launch cmd command 
      -- /sen2cor/bin/L2A_Process --resolution 10 <unzipped>
   4. Zip output
      a. remove <unzipped>
      b. remove output file
   5. Upload output file 
      a. remove zipped file
   6. Remove L1C image from bucket
   7. Schedule LIS task 
'''
@task(bind=True, max_retries=DEFAULT_MAX_RETRIES) 
def process_sen2cor(self, input_path, **kwargs):
   if input_path is None:
      return
   release = kwargs.get('release', None)
   try:
      if not os.path.exists(DATAFOLDER):
         os.makedirs(DATAFOLDER)
      storage_manager = GoogleStorageManager(SCENE_BUCKET)

      download_path, filename=download_input_file(input_path, storage_manager)
      logger.info("Input Scene {} downloaded".format(filename))
      in_scene_type, in_sensing_date, in_tile = parse_sentinel_filename(filename)
      unzipped_path = unzip_safe_folder(download_path, DATAFOLDER, filename)
      logger.info("Input Scene {} unzipped".format(filename))
      os.remove(download_path)

      logger.info("Applying Sen2cor to {}".format(filename))
      #example command: /sen2cor/bin/L2A_Process --resolution 10 /data/S2B_MSIL1C_20190714T103029_N0208_R108_T32TMS_20190714T124358.SAFE/
      command = "/sen2cor/bin/L2A_Process --resolution 10 {}".format(unzipped_path)
      process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
      process.wait()
      if process.returncode !=0:
         logger.error("Error applying Sen2cor to {}".format(filename))
         return 
      logger.info("Sen2cor applied to {}".format(filename))

      rmtree(unzipped_path)

      for root, dirs, files in os.walk(DATAFOLDER):
         for name in dirs:
            if name.find("S2A")!=-1 or name.find("S2B") !=-1:
               scene_type, sensing_date, tile = parse_sentinel_filename(name)
               if scene_type=="MSIL2A" and sensing_date == in_sensing_date and tile==in_tile:
                  output_dir=os.path.join(root, name)

      base = os.path.basename(output_dir)
      name = base.split('.')[0]
      zipped_file=DATAFOLDER+name+'.zip'

      zip_folder(output_dir,zipped_file)
      logger.info("Output Scene {} zipped".format(name))
      rmtree(output_dir)

      if release:
         upload_folder = os.path.join(SCENE_L2A_FOLDER,release)
      else:
         upload_folder = SCENE_L2A_FOLDER
      storage_manager.upload_file(upload_folder,zipped_file)
      logger.info("Output Scene {} uploaded".format(name))

      os.remove(zipped_file)
      storage_manager.delete_file(input_path)
      celery_app.send_task('snowcover_gpl.tasks.process_lis',args=('{}/{}.zip'.format(upload_folder,name),),kwargs={'release':'{}'.format(release)})
      return process.returncode
   except Exception as e:
      logger.info('Task failed due to exception: {}'.format(e))
      self.retry(countdown= DEFAULT_RETRY_COUNTDOWN ** self.request.retries)


'''
   BASIC LIS FLOW
   1. Download input data (from input parameter) to <L2A image path>
   2. Unzip to <unzipped>
      a. remove downloaded data
   3. Download the dem to <dem image path> if not present
   4. launch cmd command 
      -- python /usr/local/app/build_json.py -dem <dem image path> -preprocessing true -nodata 0 -ram 8096 -nb_threads 3 <L2A image path> <output path>
   5. launch cmd command
      --python /usr/local/app/run_snow_detector.py <output path>/param_test.json
   6. Zip output
      a. Remove unzipped
      b. remove output file
   7. Upload output file 
      a.remove zipped
   8. Remove L2A image from bucket  
'''
@task(bind=True, max_retries=DEFAULT_MAX_RETRIES) 
def process_lis(self, input_path, **kwargs):
   if input_path is None:
      return
   release = kwargs.get('release', None)
   try:
      if not os.path.exists(DATAFOLDER):
         os.makedirs(DATAFOLDER)
      storage_manager = GoogleStorageManager(SCENE_BUCKET)

      download_path, filename=download_input_file(input_path, storage_manager)
      logger.info("Input Scene {} downloaded".format(filename))
      unzipped_path = unzip_safe_folder(download_path, DATAFOLDER, filename)
      logger.info("Input Scene {} unzipped".format(filename))
      os.remove(download_path)

      dem_download_path=DATAFOLDER+'dem.tif'
      if not os.path.isfile(dem_download_path):
         storage_manager.download_file(DEM_PATH,dem_download_path)
      logger.info("DEM downloaded")

      output_path = DATAFOLDER+filename+"_"+LIS_OUTPUT_PATH
      logger.info("Generating LIS json parameters for {}".format(filename))
      #example command: python /usr/local/app/build_json.py -dem /data/srtm_45_05.tif -preprocessing true -nodata 0 -ram 8096 -nb_threads 3 /data/S2A_MSIL2A_20180311T075731_N0206_R035_T38SLH_20180311T101707.SAFE/ /data/output/
      command = "python /usr/local/app/build_json.py -dem {} -preprocessing true -nodata 0 -ram {} -nb_threads {} {} {}".format(
         dem_download_path,MAX_RAM,MAX_THREADS,unzipped_path, output_path)
      process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
      process.wait()
      if process.returncode !=0:
         logger.error("Error generating LIS json parameters for {}".format(filename))
         rmtree(unzipped_path)
         rmtree(output_path)
         return
      logger.info("Generated LIS json parameters for {}".format(filename))
      

      # If cloud coverage over a threshold the image is discarded
      logger.info("Verifying if scene {} should be treated".format(filename))
      jsonfile=os.path.join(output_path,'param_test.json')
      if os.path.exists(jsonfile):
         with open(jsonfile) as json_data:
            conf_json = json.load(json_data)
            total_cloud_percentage = conf_json["cloud"]["total_cloud_percentage"]
            if total_cloud_percentage > IGNORE_SCENE_CLOUD_THRESHOLD:
               logger.info("Scene {} is too cloudy with a cloud percentace of {}. Ignoring this scene".format(filename, total_cloud_percentage))
               rmtree(unzipped_path) 
               rmtree(output_path)
               storage_manager.copy_file(input_path, input_path.replace(SCENE_L2A_FOLDER, SCENE_DISCARDED_FOLDER))
               storage_manager.delete_file(input_path)
               return

      logger.info("Applying LIS to {}".format(filename))
      # example command: python /usr/local/app/run_snow_detector.py /data/output/param_test.json
      command = "python /usr/local/app/run_snow_detector.py {}/param_test.json ".format(output_path)
      process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
      process.wait()
      if process.returncode !=0:
         logger.error("Error applying LIS to {}".format(filename))
         rmtree(unzipped_path)
         rmtree(output_path)
         return
      logger.info("LIS applied to {}. The output is in {}".format(filename,output_path))

      lis_output_path = os.path.join(output_path,LIS_PRODUCTS_PATH)

      # apply interpolation to LIS output
      raster_to_interpolate = os.path.join(lis_output_path,LIS_OUTPUT_RASTER)
      logger.info("Interpolating small cloud gaps in LIS OUTPUT for scene {}".format(raster_to_interpolate))
      closeSmallGaps(raster_to_interpolate,lis_output_path)

      rmtree(unzipped_path)
      zipped_file = DATAFOLDER+filename+'_LIS.zip'
      zip_folder(lis_output_path,zipped_file)
      logger.info("Output from LIS {} zipped".format(zipped_file))
      rmtree(output_path)

      if release:
         upload_folder = os.path.join(SCENE_LIS_FOLDER,release)
      else:
         upload_folder = SCENE_LIS_FOLDER
      storage_manager.upload_file(upload_folder,zipped_file)
      logger.info("Output from LIS {} uploaded".format(zipped_file))
      os.remove(zipped_file)
      storage_manager.delete_file(input_path)

      return process.returncode
   except Exception as e:
      logger.info('Task failed due to exception: {}'.format(e))
      self.retry(countdown= DEFAULT_RETRY_COUNTDOWN ** self.request.retries)

def download_input_file(input_file, storage_manager):  
   base=os.path.basename(input_file)
   filename, ext = os.path.splitext(base)
   download_path=DATAFOLDER+base
   storage_manager.download_file(input_file,download_path)
   return download_path, filename

def unzip_safe_folder(input_file, output_folder, filename):
   with zipfile.ZipFile(input_file, 'r') as zipObj:
      zipObj.extractall(output_folder)
   unzipped_path = output_folder+filename+'.SAFE'
   return unzipped_path

def unzip_folder(input_file, output_folder, filename):
   with zipfile.ZipFile(input_file, 'r') as zipObj:
      zipObj.extractall(output_folder)
   unzipped_path = output_folder+filename
   return unzipped_path

def zip_folder(source_folder, output_file):
   base = os.path.basename(output_file)
   name = base.split('.')[0]
   file_format = base.split('.')[1]
   archive_from = os.path.dirname(source_folder)
   archive_to = os.path.basename(source_folder.strip(os.sep))
   make_archive(name, file_format, archive_from, archive_to)
   move('{}.{}'.format(name,file_format), output_file)

def parse_sentinel_filename(filename):
   base = os.path.basename(filename)
   splitted = base.split('_')
   scene_type = splitted[1]
   sensing_date = splitted[2]
   tile = splitted[5]
   return scene_type, sensing_date, tile

