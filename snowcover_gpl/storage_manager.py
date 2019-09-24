from google.cloud import storage
import logging

logger = logging.getLogger(__name__)

GCP_SVC_ACC_CREDENTIALS = '.gcredentials/DeFROST-credentials.json'

class GoogleStorageManager:
   def __init__(self, bucket_name):
      self.bucket_name = bucket_name
      self.storage_client = storage.Client.from_service_account_json(GCP_SVC_ACC_CREDENTIALS)
      self.bucket = self.storage_client.get_bucket(bucket_name)

   def upload_files(self, bucket_folder, file_paths):
      """Upload files to GCP bucket."""
      for f in file_paths:
         fileName = f.split('/')[-1]
         blob = self.bucket.blob('{}/{}'.format(bucket_folder,fileName))
         blob.upload_from_filename(f)
      logger.info('Uploaded {} to "{}" bucket.'.format(file_paths,self.bucket_name))
   
   def upload_file(self, bucket_folder, file_path):
      """Upload files to GCP bucket."""
      fileName = file_path.split('/')[-1]
      blob = self.bucket.blob('{}/{}'.format(bucket_folder,fileName))
      blob.upload_from_filename(file_path)
      logger.info('Uploaded {} to "{}" bucket.'.format(file_path,self.bucket_name))

   def list_files_in_directory(self, bucket_folder, delimiter=None):
      """List all files in GCP folder of a bucket."""
      files = self.bucket.list_blobs(prefix=bucket_folder, delimiter=delimiter)
      fileList = [f.name for f in files if '.' in f.name]
      return fileList

   def list_files(self):
      """List all files in GCP bucket."""
      files = self.bucket.list_blobs()
      fileList = [f.name for f in files if '.' in f.name]
      return fileList

   def download_file(self, source_file_path, destination_file_path):
      """Downloads a blob from the bucket."""
      blob = self.bucket.blob(source_file_path)

      blob.download_to_filename(destination_file_path)

      logger.info('Blob {} downloaded to {}.'.format(
         source_file_path,
         destination_file_path))

   def delete_file_from_bucket(self, bucket_folder, fileName):
      """Delete file from GCP bucket."""
      self.bucket.delete_blob('{}/{}'.format(bucket_folder,fileName))
      logger.info('{} deleted from bucket.'.format(fileName))

   def delete_file(self, file_path):
      """Delete file from GCP bucket."""
      self.bucket.delete_blob(file_path)
      logger.info('{} deleted from bucket.'.format(file_path))
   
   def copy_file(self, source_file_path, destination_file_path):
        blob = self.bucket.blob(source_file_path)
        new_blob = self.bucket.copy_blob(blob, self.bucket, destination_file_path)